"""rating: K by experience, 75% loss discount, rated tournament fights, inactivity decay

Новые правила очков:
- K = 48 для первых 10 боёв игрока, дальше K = 32;
- поражение стоит 75% от Elo, но не больше 2 таких скидок от одного соперника за 7 дней;
- турнирные бои тоже дают очки по Elo, приз турнира начисляется сверху;
- простой: rating_decays хранит снятия за недели без боёв.

История пересчитывается с нуля по новым правилам в порядке событий: подтверждение боя,
приз завершённого турнира, действующая ручная корректировка (по времени последнего изменения).
Снятий за простой на момент миграции нет, таблица создаётся пустой.
Расчёт повторяет app/services/rating.py, но не импортирует его: миграция не должна зависеть
от будущих версий кода. Тест tests/test_recalculation.py сверяет их между собой.

Revision ID: 0007
Revises: 0006
"""
import math
from collections import defaultdict
from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

START_POINTS = 1000
ELO_SCALE = 400
K_NEW = 48
K_EXPERIENCED = 32
NEW_PLAYER_FIGHTS = 10
LOSS_SHARE = 0.75
LOSS_DISCOUNTS_PER_OPPONENT = 2
LOSS_DISCOUNT_WINDOW = timedelta(days=7)


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def _expected(points: int, opponent_points: int) -> float:
    return 1 / (1 + 10 ** ((opponent_points - points) / ELO_SCALE))


def _places(points: dict[int, int], active: set[int], pair: tuple[int, int]) -> dict[int, int]:
    """Места по очкам с общим местом при равенстве (как dense_rank в рейтинге)."""
    ranked = sorted({points[player_id] for player_id in active | set(pair)}, reverse=True)
    place_of = {value: index + 1 for index, value in enumerate(ranked)}
    return {player_id: place_of[points[player_id]] for player_id in pair}


def recalculate(connection) -> None:
    users = connection.execute(sa.text('SELECT id, status FROM users')).all()
    points = {user_id: START_POINTS for user_id, _ in users}
    active = {user_id for user_id, status in users if status == 'active'}

    events = []
    for row in connection.execute(
        sa.text(
            "SELECT id, winner_id, loser_id, confirmed_at FROM fights "
            "WHERE status = 'confirmed' ORDER BY confirmed_at, id"
        )
    ):
        events.append((row.confirmed_at, 0, row.id, row))
    for row in connection.execute(
        sa.text(
            "SELECT id, winner_id, win_points, finished_at FROM tournaments "
            "WHERE status = 'finished' AND winner_id IS NOT NULL AND win_points <> 0"
        )
    ):
        events.append((row.finished_at, 1, row.id, row))
    for row in connection.execute(
        sa.text(
            "SELECT a.fight_id, a.winner_delta, a.updated_at, f.winner_id, f.loser_id "
            "FROM rating_adjustments a JOIN fights f ON f.id = a.fight_id "
            "WHERE a.status = 'active' AND f.status = 'confirmed'"
        )
    ):
        events.append((row.updated_at, 2, row.fight_id, row))
    events.sort(key=lambda event: event[:3])

    rated_fights: dict[int, int] = defaultdict(int)
    # (проигравший, победитель) -> время подтверждения боёв, где проигравший получил скидку.
    discounts: dict[tuple[int, int], list] = defaultdict(list)
    changes = []
    for moment, kind, _, row in events:
        if kind == 1:
            points[row.winner_id] += row.win_points
            continue
        if kind == 2:
            points[row.winner_id] += row.winner_delta
            points[row.loser_id] -= row.winner_delta
            continue

        winner, loser = row.winner_id, row.loser_id
        pair = (winner, loser)
        places_before = _places(points, active, pair)
        upset_share = 1 - _expected(points[winner], points[loser])
        winner_k = K_NEW if rated_fights[winner] < NEW_PLAYER_FIGHTS else K_EXPERIENCED
        loser_k = K_NEW if rated_fights[loser] < NEW_PLAYER_FIGHTS else K_EXPERIENCED
        recent = [used for used in discounts[(loser, winner)] if used > moment - LOSS_DISCOUNT_WINDOW]
        gain = max(1, _round(winner_k * upset_share))
        full_loss = max(1, _round(loser_k * upset_share))
        if len(recent) < LOSS_DISCOUNTS_PER_OPPONENT:
            loss = max(1, _round(loser_k * upset_share * LOSS_SHARE))
        else:
            loss = full_loss
        if full_loss > loss:
            discounts[(loser, winner)].append(moment)

        before = {winner: points[winner], loser: points[loser]}
        points[winner] += gain
        points[loser] -= loss
        rated_fights[winner] += 1
        rated_fights[loser] += 1
        places_after = _places(points, active, pair)
        for player_id, delta, discount in ((winner, gain, 0), (loser, -loss, full_loss - loss)):
            changes.append(
                {
                    'fight_id': row.id,
                    'player_id': player_id,
                    'place_before': places_before[player_id],
                    'points_before': before[player_id],
                    'delta': delta,
                    'loss_discount': discount,
                    'points_after': points[player_id],
                    'place_after': places_after[player_id],
                    'created_at': moment,
                }
            )

    connection.execute(sa.text('DELETE FROM rating_changes'))
    if changes:
        connection.execute(
            sa.text(
                'INSERT INTO rating_changes (fight_id, player_id, place_before, points_before, delta, '
                'loss_discount, points_after, place_after, created_at) VALUES (:fight_id, :player_id, '
                ':place_before, :points_before, :delta, :loss_discount, :points_after, :place_after, :created_at)'
            ),
            changes,
        )
    if points:
        connection.execute(
            sa.text('UPDATE users SET rating_points = :points WHERE id = :id'),
            [{'id': user_id, 'points': value} for user_id, value in points.items()],
        )


def upgrade() -> None:
    op.add_column(
        'rating_changes', sa.Column('loss_discount', sa.Integer(), server_default='0', nullable=False)
    )
    op.create_table(
        'rating_decays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('points_before', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('points_after', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], name=op.f('fk_rating_decays_player_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_rating_decays')),
        sa.UniqueConstraint('player_id', 'due_at', name='uq_rating_decays_player_due'),
    )
    op.create_index(op.f('ix_rating_decays_player_id'), 'rating_decays', ['player_id'], unique=False)
    recalculate(op.get_bind())


def downgrade() -> None:
    # Очки и история начислений остаются пересчитанными: старые значения восстанавливаются только из бэкапа.
    op.drop_index(op.f('ix_rating_decays_player_id'), table_name='rating_decays')
    op.drop_table('rating_decays')
    op.drop_column('rating_changes', 'loss_discount')
