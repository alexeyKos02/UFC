"""Очки, места и общий замок рейтинга.

Замок берётся до чтения мест всеми операциями, которые меняют очки или состав таблицы:
финальное подтверждение, ручная корректировка, спецместа, регистрация, блокировка.
Он всегда первый в цепочке замков, поэтому взаимных блокировок между этими операциями нет.
"""

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Fight, RatingChange, SpecialPlace, User, UserStatus

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
    db.add_all(
        [
            RatingChange(
                fight_id=fight.id,
                player_id=winner.id,
                place_before=winner_place,
                points_before=winner.rating_points,
                delta=delta,
                points_after=winner.rating_points + delta,
            ),
            RatingChange(
                fight_id=fight.id,
                player_id=loser.id,
                place_before=loser_place,
                points_before=loser.rating_points,
                delta=-delta,
                points_after=loser.rating_points - delta,
            ),
        ]
    )
    winner.rating_points += delta
    loser.rating_points -= delta
    db.flush()


@dataclass
class RatingRow:
    user: User
    points_place: int
    display_place: int
    is_special: bool


def rating_table(db: Session) -> list[RatingRow]:
    """Строки таблицы: сначала закрепляются спецместа, группы по очкам занимают свободные номера."""
    players = list(
        db.scalars(
            select(User).where(User.status == UserStatus.ACTIVE).order_by(User.rating_points.desc(), User.nickname)
        )
    )
    points_place_by_id = points_places(db)
    pinned = dict(db.execute(select(SpecialPlace.user_id, SpecialPlace.place)).all())
    active_ids = {player.id for player in players}
    taken_numbers = {number for user_id, number in pinned.items() if user_id in active_ids}

    rows: list[RatingRow] = []
    next_number = 0
    previous_points: int | None = None
    for player in players:
        if player.id in pinned:
            rows.append(RatingRow(player, points_place_by_id[player.id], pinned[player.id], True))
            continue
        if player.rating_points != previous_points:
            next_number += 1
            while next_number in taken_numbers:
                next_number += 1
            previous_points = player.rating_points
        rows.append(RatingRow(player, points_place_by_id[player.id], next_number, False))

    rows.sort(key=lambda row: (row.display_place, not row.is_special, row.user.nickname.lower()))
    return rows


def rating_row_for(db: Session, user: User) -> RatingRow | None:
    if user.status != UserStatus.ACTIVE:
        return None
    return next((row for row in rating_table(db) if row.user.id == user.id), None)
