"""rating_changes: number in the rating table before and after each fight

Раньше в начислениях хранилось только место по очкам (равные очки делят место).
Игроки видят другой номер: чемпион стоит над таблицей без номера, игроки в калибровке
ниже остальных, спецместа закреплены, равные очки разводятся личными встречами.
Новые поля хранят именно его; место по очкам остаётся для апсетов.

История заполняется пересчётом: события идут по времени, и перед каждым боем и после него
таблица собирается так же, как app/services/rating.rating_table. Чего в базе нет — когда
игрок был заблокирован, — берётся по текущему статусу. Тест tests/test_table_places.py
сверяет пересчёт с номерами, которые записывает живой код.

Revision ID: 0008
Revises: 0007
"""
from collections import Counter, defaultdict
from itertools import count, groupby

from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

START_POINTS = 1000
CALIBRATION_FIGHTS = 5
METHOD_ORDER = ('ko_tko', 'submission', 'decision')


def _break_tie(players: list[int], fights: list[tuple], alphabet) -> list[int]:
    if len(players) < 2:
        return players
    ids = set(players)
    net_wins: Counter = Counter()
    wins_by_method: Counter = Counter()
    for winner_id, loser_id, method in fights:
        if winner_id in ids and loser_id in ids:
            net_wins[winner_id] += 1
            net_wins[loser_id] -= 1
            wins_by_method[winner_id, method] += 1

    def strength(player: int) -> tuple:
        return (net_wins[player], *(wins_by_method[player, method] for method in METHOD_ORDER))

    ranked = sorted(players, key=strength, reverse=True)
    groups = [list(group) for _, group in groupby(ranked, key=strength)]
    if len(groups) == 1:
        return sorted(players, key=alphabet)
    return [player for group in groups for player in _break_tie(group, fights, alphabet)]


def table(points, roster, champion, pinned, fights, fights_played, alphabet) -> dict[int, tuple]:
    players = sorted(roster, key=lambda player: (-points[player], alphabet(player)))
    taken = {number for player, number in pinned.items() if player in roster and player != champion}
    places: dict[int, tuple] = {}
    to_number = []
    for player in players:
        if player == champion:
            places[player] = (None, True)
        elif player in pinned:
            places[player] = (pinned[player], False)
        else:
            to_number.append(player)
    free = (number for number in count(1) if number not in taken)
    for calibrating in (False, True):
        group = [player for player in to_number if (fights_played[player] < CALIBRATION_FIGHTS) == calibrating]
        for _, tied in groupby(group, key=lambda player: points[player]):
            for player in _break_tie(list(tied), fights, alphabet):
                places[player] = (next(free), False)
    return places


def backfill(connection) -> None:
    users = connection.execute(sa.text('SELECT id, nickname, status, created_at FROM users')).all()
    nickname = {row.id: row.nickname.casefold().replace('ё', 'е') for row in users}
    active = {row.id for row in users if row.status == 'active'}

    def alphabet(player: int) -> str:
        return nickname[player]

    changes = defaultdict(dict)
    for row in connection.execute(
        sa.text('SELECT fight_id, player_id, points_before, points_after FROM rating_changes')
    ):
        changes[row.fight_id][row.player_id] = (row.points_before, row.points_after)

    # Последствия самого боя: смена чемпиона и приз турнира входят в номер «после боя».
    fight_belt = dict(
        connection.execute(
            sa.text(
                "SELECT w.fight_id, w.user_id FROM belt_wins w JOIN belts b ON b.id = w.belt_id "
                "WHERE b.kind = 'main' AND w.fight_id IS NOT NULL"
            )
        ).all()
    )
    fight_prize = {
        row.fight_id: (row.winner_id, row.win_points)
        for row in connection.execute(
            sa.text(
                "SELECT f.id AS fight_id, t.winner_id, t.win_points FROM tournaments t "
                "JOIN tournament_matches m ON m.tournament_id = t.id AND m.round = t.rounds_count "
                "JOIN fights f ON f.tournament_match_id = m.id "
                "WHERE t.status = 'finished' AND t.winner_id IS NOT NULL"
            )
        )
    }

    # (время, порядок, id, вид, данные)
    events = []
    for row in users:
        events.append((row.created_at, 0, row.id, 'user', row))
    for row in connection.execute(
        sa.text(
            "SELECT id, winner_id, loser_id, method, confirmed_at FROM fights "
            "WHERE status = 'confirmed' ORDER BY confirmed_at, id"
        )
    ):
        events.append((row.confirmed_at, 1, row.id, 'fight', row))
    for row in connection.execute(
        sa.text(
            "SELECT w.id, w.user_id, w.created_at FROM belt_wins w JOIN belts b ON b.id = w.belt_id "
            "WHERE b.kind = 'main' AND w.fight_id IS NULL"
        )
    ):
        events.append((row.created_at, 2, row.id, 'award', row))
    for row in connection.execute(
        sa.text(
            "SELECT a.fight_id, a.winner_delta, a.updated_at, f.winner_id, f.loser_id "
            "FROM rating_adjustments a JOIN fights f ON f.id = a.fight_id "
            "WHERE a.status = 'active' AND f.status = 'confirmed'"
        )
    ):
        events.append((row.updated_at, 3, row.fight_id, 'adjustment', row))
    for row in connection.execute(sa.text('SELECT id, player_id, points_after, created_at FROM rating_decays')):
        events.append((row.created_at, 4, row.id, 'decay', row))
    for row in connection.execute(
        sa.text('SELECT id, user_id, action, place_after, created_at FROM special_place_log')
    ):
        events.append((row.created_at, 5, row.id, 'special', row))
    events.sort(key=lambda event: event[:3])

    points: dict[int, int] = defaultdict(lambda: START_POINTS)
    roster: set[int] = set()
    champion = None
    pinned: dict[int, int] = {}
    fights: list[tuple] = []
    fights_played: Counter = Counter()
    updates = []

    def snapshot() -> dict[int, tuple]:
        return table(points, roster, champion, pinned, fights, fights_played, alphabet)

    for _, _, _, kind, row in events:
        if kind == 'user':
            if row.id in active:
                roster.add(row.id)
        elif kind == 'award':
            champion = row.user_id
        elif kind == 'adjustment':
            points[row.winner_id] += row.winner_delta
            points[row.loser_id] -= row.winner_delta
        elif kind == 'decay':
            points[row.player_id] = row.points_after
        elif kind == 'special':
            if row.action == 'clear':
                pinned.pop(row.user_id, None)
            else:
                pinned[row.user_id] = row.place_after
        else:
            # Участники боя точно уже были в лиге, даже если время регистрации записано позже.
            roster.update(player_id for player_id in (row.winner_id, row.loser_id) if player_id in active)
            pair = changes.get(row.id, {})
            for player_id, (before_points, _) in pair.items():
                points[player_id] = before_points
            before = snapshot()
            for player_id, (_, after_points) in pair.items():
                points[player_id] = after_points
            fights.append((row.winner_id, row.loser_id, row.method))
            fights_played[row.winner_id] += 1
            fights_played[row.loser_id] += 1
            if row.id in fight_belt:
                champion = fight_belt[row.id]
            if row.id in fight_prize:
                winner_id, prize = fight_prize[row.id]
                points[winner_id] += prize
            after = snapshot()
            for player_id in pair:
                place_before, champion_before = before.get(player_id, (None, False))
                place_after, champion_after = after.get(player_id, (None, False))
                updates.append(
                    {
                        'fight_id': row.id,
                        'player_id': player_id,
                        'place_before': place_before,
                        'place_after': place_after,
                        'champion_before': champion_before,
                        'champion_after': champion_after,
                    }
                )

    if updates:
        connection.execute(
            sa.text(
                'UPDATE rating_changes SET table_place_before = :place_before, table_place_after = :place_after, '
                'champion_before = :champion_before, champion_after = :champion_after '
                'WHERE fight_id = :fight_id AND player_id = :player_id'
            ),
            updates,
        )


def upgrade() -> None:
    op.add_column('rating_changes', sa.Column('table_place_before', sa.Integer(), nullable=True))
    op.add_column('rating_changes', sa.Column('table_place_after', sa.Integer(), nullable=True))
    op.add_column(
        'rating_changes', sa.Column('champion_before', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'rating_changes', sa.Column('champion_after', sa.Boolean(), server_default='false', nullable=False)
    )
    backfill(op.get_bind())


def downgrade() -> None:
    op.drop_column('rating_changes', 'champion_after')
    op.drop_column('rating_changes', 'champion_before')
    op.drop_column('rating_changes', 'table_place_after')
    op.drop_column('rating_changes', 'table_place_before')
