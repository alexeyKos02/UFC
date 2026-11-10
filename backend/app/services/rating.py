"""Очки, места и общий замок рейтинга.

Замок берётся до чтения мест всеми операциями, которые меняют очки или состав таблицы:
финальное подтверждение, ручная корректировка, спецместа, регистрация, блокировка.
Он всегда первый в цепочке замков, поэтому взаимных блокировок между этими операциями нет.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import count, groupby

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    Belt,
    BeltKind,
    Fight,
    FightMethod,
    FightStatus,
    RatingChange,
    SpecialPlace,
    User,
    UserStatus,
)

RATING_LOCK_KEY = 7_202_411
UPSET_GAP = 3
UPSET_POINTS = 5
REGULAR_POINTS = 2


def acquire_rating_lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": RATING_LOCK_KEY})
    # Объекты сессии могли загрузиться до замка (например, текущий пользователь) и устареть.
    db.expire_all()


def points_places(db: Session) -> dict[int, int]:
    """Места по очкам среди всех активных игроков, равные очки дают одно место без пропусков."""
    rows = db.execute(
        select(User.id, func.dense_rank().over(order_by=User.rating_points.desc())).where(
            User.status == UserStatus.ACTIVE
        )
    ).all()
    return {user_id: place for user_id, place in rows}


def auto_delta(winner_place: int, loser_place: int) -> int:
    return UPSET_POINTS if winner_place - loser_place >= UPSET_GAP else REGULAR_POINTS


def is_upset(winner_place: int, loser_place: int) -> bool:
    return winner_place - loser_place >= UPSET_GAP


def apply_fight_rating(db: Session, fight: Fight, winner: User, loser: User) -> None:
    places = points_places(db)
    winner_place, loser_place = places[winner.id], places[loser.id]
    delta = auto_delta(winner_place, loser_place)
    winner_before, loser_before = winner.rating_points, loser.rating_points
    winner.rating_points += delta
    loser.rating_points -= delta
    db.flush()
    places_after = points_places(db)
    db.add_all(
        [
            RatingChange(
                fight_id=fight.id,
                player_id=winner.id,
                place_before=winner_place,
                points_before=winner_before,
                delta=delta,
                points_after=winner.rating_points,
                place_after=places_after[winner.id],
            ),
            RatingChange(
                fight_id=fight.id,
                player_id=loser.id,
                place_before=loser_place,
                points_before=loser_before,
                delta=-delta,
                points_after=loser.rating_points,
                place_after=places_after[loser.id],
            ),
        ]
    )
    db.flush()


@dataclass
class RatingRow:
    user: User
    points_place: int
    display_place: int | None
    is_special: bool
    is_champion: bool = False


# От самого убедительного способа победы к наименее убедительному. Победа без указанного способа не считается.
METHOD_ORDER = (FightMethod.KO_TKO, FightMethod.SUBMISSION, FightMethod.DECISION)


def _alphabet_key(player: User) -> str:
    return player.nickname.casefold().replace("ё", "е")


def break_tie(players: list[User], fights: Iterable[tuple[int, int, FightMethod | None]]) -> list[User]:
    """Порядок игроков с равными очками: личные встречи, способ побед в них, затем алфавит."""
    if len(players) < 2:
        return players
    fights = list(fights)
    ids = {player.id for player in players}
    net_wins: Counter = Counter()
    wins_by_method: Counter = Counter()
    for winner_id, loser_id, method in fights:
        if winner_id in ids and loser_id in ids:
            net_wins[winner_id] += 1
            net_wins[loser_id] -= 1
            wins_by_method[winner_id, method] += 1

    def strength(player: User) -> tuple[int, ...]:
        return (net_wins[player.id], *(wins_by_method[player.id, method] for method in METHOD_ORDER))

    ranked = sorted(players, key=strength, reverse=True)
    groups = [list(group) for _, group in groupby(ranked, key=strength)]
    if len(groups) == 1:
        return sorted(players, key=_alphabet_key)
    # Внутри оставшихся групп бои пересчитываются заново, уже только между равными.
    return [player for group in groups for player in break_tie(group, fights)]


def rating_table(db: Session) -> list[RatingRow]:
    """Чемпион основного пояса идёт первым без номера, остальные нумеруются с единицы.

    Сначала закрепляются спецместа, остальные занимают свободные номера по одному.
    """
    players = list(
        db.scalars(
            select(User).where(User.status == UserStatus.ACTIVE).order_by(User.rating_points.desc(), User.nickname)
        )
    )
    points_place_by_id = points_places(db)
    champion_id = db.scalar(select(Belt.current_champion_id).where(Belt.kind == BeltKind.MAIN))
    pinned = dict(db.execute(select(SpecialPlace.user_id, SpecialPlace.place)).all())
    active_ids = {player.id for player in players}
    # Пока игрок держит пояс, его спецместо не действует и номер свободен для остальных.
    taken_numbers = {
        number for user_id, number in pinned.items() if user_id in active_ids and user_id != champion_id
    }

    rows: list[RatingRow] = []
    to_number: list[User] = []
    for player in players:
        if player.id == champion_id:
            rows.append(RatingRow(player, points_place_by_id[player.id], None, False, True))
        elif player.id in pinned:
            rows.append(RatingRow(player, points_place_by_id[player.id], pinned[player.id], True))
        else:
            to_number.append(player)

    fights = db.execute(
        select(Fight.winner_id, Fight.loser_id, Fight.method).where(Fight.status == FightStatus.CONFIRMED)
    ).all()
    free_numbers = (number for number in count(1) if number not in taken_numbers)
    # Игроки уже идут по убыванию очков, поэтому равные стоят подряд.
    for _, tied in groupby(to_number, key=lambda player: player.rating_points):
        for player in break_tie(list(tied), fights):
            rows.append(RatingRow(player, points_place_by_id[player.id], next(free_numbers), False))

    rows.sort(key=lambda row: (not row.is_champion, row.display_place or 0))
    return rows


def rating_row_for(db: Session, user: User) -> RatingRow | None:
    if user.status != UserStatus.ACTIVE:
        return None
    return next((row for row in rating_table(db) if row.user.id == user.id), None)


TOP_TIER_LAST_PLACE = 5
MIDDLE_TIER_LAST_PLACE = 20


def rating_tier(row: RatingRow | None) -> str | None:
    """Плашка в профиле по номеру из таблицы. Чемпион стоит выше №1, поэтому всегда в топе."""
    if row is None:
        return None
    if row.is_champion or row.display_place <= TOP_TIER_LAST_PLACE:
        return "top"
    return "middle" if row.display_place <= MIDDLE_TIER_LAST_PLACE else "bottom"
