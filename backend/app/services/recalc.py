"""Пересчёт очков и мест по дате боя.

Очки по Elo зависят от порядка боёв. Бои подтверждают в любом порядке, поэтому при каждом
подтверждении история проигрывается по дате боя (fought_at, при равной дате — по номеру боя).
Если подтверждён бой, сыгранный раньше уже подтверждённых, все следующие бои получают новые
начисления, а изменившиеся помечаются (fights.points_recalculated_at).

Проход по истории дешёвый: очки, опыт игрока, окна скидки и счётчики личных встреч обновляются
за постоянное время на бой. Дорогая часть — сборка таблицы рейтинга до и после боя — делается
только для боёв начиная с места вставки. Личные встречи для разбора равных очков берутся из
готовых счётчиков, а не перебором всей истории.

Модуль работает через Connection и обычный SQL, без ORM-моделей: его вызывает и миграция 0010.
Константы правил берутся из app/services/rating.py, номер в таблице повторяет rating_table.
"""

import math
from collections import Counter, defaultdict
from datetime import datetime
from itertools import count, groupby

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services.rating import (
    CALIBRATION_FIGHTS,
    ELO_SCALE,
    K_EXPERIENCED,
    K_NEW,
    LOSS_DISCOUNT_WINDOW,
    LOSS_DISCOUNTS_PER_OPPONENT,
    LOSS_SHARE,
    NEW_PLAYER_FIGHTS,
    START_POINTS,
)


METHOD_ORDER = ("ko_tko", "submission", "decision")


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def _expected(points: int, opponent_points: int) -> float:
    return 1 / (1 + 10 ** ((opponent_points - points) / ELO_SCALE))


class HeadToHead:
    """Счётчики личных встреч: победы игрока над соперником, всего и по способу."""

    def __init__(self) -> None:
        self.wins: Counter = Counter()
        self.by_method: Counter = Counter()

    def add(self, winner: int, loser: int, method: str | None) -> None:
        self.wins[winner, loser] += 1
        self.by_method[winner, loser, method] += 1

    def strength(self, player: int, group: list[int]) -> tuple[int, ...]:
        """Как break_tie в rating.py: разница побед внутри группы, затем победы по способам."""
        net = 0
        methods = [0] * len(METHOD_ORDER)
        for other in group:
            if other == player:
                continue
            net += self.wins[player, other] - self.wins[other, player]
            for index, method in enumerate(METHOD_ORDER):
                methods[index] += self.by_method[player, other, method]
        return (net, *methods)


def break_tie(players: list[int], h2h: HeadToHead, alphabet) -> list[int]:
    if len(players) < 2:
        return players
    strengths = {player: h2h.strength(player, players) for player in players}
    ranked = sorted(players, key=strengths.get, reverse=True)
    groups = [list(group) for _, group in groupby(ranked, key=strengths.get)]
    if len(groups) == 1:
        return sorted(players, key=alphabet)
    return [player for group in groups for player in break_tie(group, h2h, alphabet)]


def table_places(points, roster, champion, pinned, h2h, fights_played, alphabet) -> dict[int, tuple]:
    """Номер в таблице (или чемпион без номера) — как rating_table."""
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
            for player in break_tie(list(tied), h2h, alphabet):
                places[player] = (next(free), False)
    return places


def points_places(points, roster) -> dict[int, int]:
    """Место по очкам: равные очки делят место (dense rank)."""
    ranked = sorted({points[player] for player in roster}, reverse=True)
    place_of = {value: index + 1 for index, value in enumerate(ranked)}
    return {player: place_of[points[player]] for player in roster}


def tournament_prizes(connection: Connection) -> dict[int, list[tuple[int, int]]]:
    """Призы завершённых турниров в очки лиги: бой, завершивший турнир, -> [(игрок, очки)].

    1-е место — победитель финала, 2-е — проигравший в финале. 3-е — победитель матча за 3-е место,
    а без такого матча — оба проигравших полуфиналиста. Турнир завершает последний по дате бой
    из финала и матча за 3-е место.
    """
    tournaments = connection.execute(
        text(
            "SELECT id, rounds_count, win_points, second_points, third_points, has_third_place "
            "FROM tournaments WHERE status = 'finished' AND winner_id IS NOT NULL"
        )
    ).all()
    if not tournaments:
        return {}
    matches = defaultdict(list)
    for row in connection.execute(
        text(
            "SELECT m.tournament_id, m.round, m.player1_id, m.player2_id, m.winner_id, m.is_bye, m.is_third_place, "
            "f.id AS fight_id, f.fought_at FROM tournament_matches m "
            "LEFT JOIN fights f ON f.tournament_match_id = m.id AND f.status = 'confirmed' "
            "WHERE m.tournament_id = ANY(:ids)"
        ),
        {"ids": [row.id for row in tournaments]},
    ):
        matches[row.tournament_id].append(row)

    def loser(match) -> int | None:
        if match.is_bye or match.winner_id is None or match.player1_id is None or match.player2_id is None:
            return None
        return match.player2_id if match.winner_id == match.player1_id else match.player1_id

    prizes: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for tournament in tournaments:
        rows = matches[tournament.id]
        final = next((m for m in rows if m.round == tournament.rounds_count and not m.is_third_place), None)
        if final is None or final.fight_id is None:
            continue
        third_match = next((m for m in rows if m.is_third_place), None) if tournament.has_third_place else None
        places = [(final.winner_id, tournament.win_points), (loser(final), tournament.second_points)]
        if third_match is not None:
            places.append((third_match.winner_id, tournament.third_points))
        else:
            semis = [m for m in rows if m.round == tournament.rounds_count - 1 and not m.is_third_place]
            places += [(loser(m), tournament.third_points) for m in semis]
        closing = [m for m in (final, third_match) if m is not None and m.fight_id is not None]
        last = max(closing, key=lambda m: (m.fought_at, m.fight_id))
        prizes[last.fight_id] += [(player, prize) for player, prize in places if player is not None and prize]
    return prizes


def recalculate(
    connection: Connection,
    from_key: tuple[datetime, int] | None = None,
    trigger_fight_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Проигрывает историю по дате боя и записывает начисления, начиная с боя from_key.

    from_key=None — пересчитать всё. trigger_fight_id — бой, из-за которого пересчёт: у остальных
    боёв с изменившимися очками ставится пометка. Возвращает сводку для журнала и тестов.
    """
    users = connection.execute(text("SELECT id, nickname, status, created_at FROM users")).all()
    nickname = {row.id: row.nickname.casefold().replace("ё", "е") for row in users}
    active = {row.id for row in users if row.status == "active"}

    def alphabet(player: int) -> str:
        return nickname[player]

    existing = {
        (row.fight_id, row.player_id): row
        for row in connection.execute(
            text("SELECT id, fight_id, player_id, delta, points_before FROM rating_changes")
        )
    }
    fight_belt = dict(
        connection.execute(
            text(
                "SELECT w.fight_id, w.user_id FROM belt_wins w JOIN belts b ON b.id = w.belt_id "
                "WHERE b.kind = 'main' AND w.fight_id IS NOT NULL"
            )
        ).all()
    )
    fight_prize = tournament_prizes(connection)

    events = [(row.created_at, 0, row.id, "user", row) for row in users]
    for row in connection.execute(
        text("SELECT id, kind, winner_id, loser_id, method, fought_at FROM fights WHERE status = 'confirmed'")
    ):
        events.append((row.fought_at, 1, row.id, "fight", row))
    for row in connection.execute(
        text(
            "SELECT w.id, w.user_id, w.created_at FROM belt_wins w JOIN belts b ON b.id = w.belt_id "
            "WHERE b.kind = 'main' AND w.fight_id IS NULL"
        )
    ):
        events.append((row.created_at, 2, row.id, "award", row))
    for row in connection.execute(
        text(
            "SELECT a.fight_id, a.winner_delta, a.updated_at, f.winner_id, f.loser_id "
            "FROM rating_adjustments a JOIN fights f ON f.id = a.fight_id "
            "WHERE a.status = 'active' AND f.status = 'confirmed' AND f.kind <> 'tournament'"
        )
    ):
        events.append((row.updated_at, 3, row.fight_id, "adjustment", row))
    for row in connection.execute(text("SELECT id, player_id, delta, due_at FROM rating_decays")):
        events.append((row.due_at, 4, row.id, "decay", row))
    for row in connection.execute(text("SELECT id, user_id, action, place_after, created_at FROM special_place_log")):
        events.append((row.created_at, 5, row.id, "special", row))
    events.sort(key=lambda event: event[:3])

    points: dict[int, int] = defaultdict(lambda: START_POINTS)
    roster: set[int] = set()
    champion = None
    pinned: dict[int, int] = {}
    h2h = HeadToHead()
    fights_played: Counter = Counter()
    discounts: dict[tuple[int, int], list[datetime]] = defaultdict(list)
    writes: list[dict] = []
    inserts: list[dict] = []
    changed_fights: set[int] = set()

    def snapshot() -> tuple[dict, dict]:
        return points_places(points, roster), table_places(
            points, roster, champion, pinned, h2h, fights_played, alphabet
        )

    for moment, _, _, kind, row in events:
        if kind == "user":
            if row.id in active:
                roster.add(row.id)
            continue
        if kind == "award":
            champion = row.user_id
            continue
        if kind == "adjustment":
            points[row.winner_id] += row.winner_delta
            points[row.loser_id] -= row.winner_delta
            continue
        if kind == "decay":
            points[row.player_id] += row.delta
            continue
        if kind == "special":
            if row.action == "clear":
                pinned.pop(row.user_id, None)
            else:
                pinned[row.user_id] = row.place_after
            continue

        winner, loser = row.winner_id, row.loser_id
        tracked = from_key is None or (row.fought_at, row.id) >= from_key
        roster.update(player for player in (winner, loser) if player in active)
        if row.kind == "tournament":
            # Бой турнира очков лиги не даёт и не считается в калибровку, скидки и личные встречи
            # таблицы. Пояс и призы за места начисляются боем, который завершил турнир.
            if row.id in fight_belt:
                champion = fight_belt[row.id]
            for player, prize in fight_prize.get(row.id, ()):
                points[player] += prize
            continue
        if tracked:
            points_before_place, table_before = snapshot()

        upset_share = 1 - _expected(points[winner], points[loser])
        winner_k = K_NEW if fights_played[winner] < NEW_PLAYER_FIGHTS else K_EXPERIENCED
        loser_k = K_NEW if fights_played[loser] < NEW_PLAYER_FIGHTS else K_EXPERIENCED
        recent = [used for used in discounts[loser, winner] if used > moment - LOSS_DISCOUNT_WINDOW]
        discounts[loser, winner] = recent
        gain = max(1, _round(winner_k * upset_share))
        full_loss = max(1, _round(loser_k * upset_share))
        if len(recent) < LOSS_DISCOUNTS_PER_OPPONENT:
            loss = max(1, _round(loser_k * upset_share * LOSS_SHARE))
        else:
            loss = full_loss
        if full_loss > loss:
            recent.append(moment)

        before = {winner: points[winner], loser: points[loser]}
        points[winner] += gain
        points[loser] -= loss
        fights_played[winner] += 1
        fights_played[loser] += 1
        h2h.add(winner, loser, row.method)
        if row.id in fight_belt:
            champion = fight_belt[row.id]

        if not tracked:
            continue
        points_after_place, table_after = snapshot()
        for player, delta, discount in ((winner, gain, 0), (loser, -loss, full_loss - loss)):
            values = {
                "fight_id": row.id,
                "player_id": player,
                "place_before": points_before_place.get(player, 0),
                "points_before": before[player],
                "delta": delta,
                "loss_discount": discount,
                # Очки «после» — сразу после боя, без приза турнира: приз виден в очках игрока.
                "points_after": before[player] + delta,
                "place_after": points_after_place.get(player, 0),
                "table_place_before": table_before.get(player, (None, False))[0],
                "champion_before": table_before.get(player, (None, False))[1],
                "table_place_after": table_after.get(player, (None, False))[0],
                "champion_after": table_after.get(player, (None, False))[1],
            }
            old = existing.get((row.id, player))
            if old is None:
                inserts.append({**values, "created_at": moment})
            else:
                writes.append(values)
                if row.id != trigger_fight_id and (old.delta != delta or old.points_before != before[player]):
                    changed_fights.add(row.id)

    columns = (
        "place_before = :place_before, points_before = :points_before, delta = :delta, "
        "loss_discount = :loss_discount, points_after = :points_after, place_after = :place_after, "
        "table_place_before = :table_place_before, champion_before = :champion_before, "
        "table_place_after = :table_place_after, champion_after = :champion_after"
    )
    if writes:
        connection.execute(
            text(f"UPDATE rating_changes SET {columns} WHERE fight_id = :fight_id AND player_id = :player_id"),
            writes,
        )
    if inserts:
        connection.execute(
            text(
                "INSERT INTO rating_changes (fight_id, player_id, place_before, points_before, delta, "
                "loss_discount, points_after, place_after, table_place_before, champion_before, "
                "table_place_after, champion_after, created_at) VALUES (:fight_id, :player_id, :place_before, "
                ":points_before, :delta, :loss_discount, :points_after, :place_after, :table_place_before, "
                ":champion_before, :table_place_after, :champion_after, :created_at)"
            ),
            inserts,
        )
    if changed_fights and trigger_fight_id is not None:
        connection.execute(
            text(
                "UPDATE fights SET points_recalculated_at = :now, recalculated_by_fight_id = :trigger "
                "WHERE id = ANY(:ids)"
            ),
            {"now": now, "trigger": trigger_fight_id, "ids": sorted(changed_fights)},
        )
    # У каждого игрока очки — итог истории; у кого событий нет, остаются стартовые.
    if users:
        connection.execute(
            text("UPDATE users SET rating_points = :points WHERE id = :id AND rating_points <> :points"),
            [{"id": row.id, "points": points[row.id]} for row in users],
        )
    return {"written": len(writes) + len(inserts), "recalculated_fights": sorted(changed_fights)}
