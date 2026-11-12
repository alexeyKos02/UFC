"""Очки, места и общий замок рейтинга.

Замок берётся до чтения мест всеми операциями, которые меняют очки или состав таблицы:
финальное подтверждение, ручная корректировка, спецместа, регистрация, блокировка.
Он всегда первый в цепочке замков, поэтому взаимных блокировок между этими операциями нет.
"""

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import count, groupby

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import (
    Belt,
    BeltKind,
    Fight,
    FightMethod,
    FightStatus,
    RatingChange,
    RatingDecay,
    SpecialPlace,
    User,
    UserStatus,
)

RATING_LOCK_KEY = 7_202_411
# Апсет — победа над соперником выше на 3 места или больше. Очков он сам не добавляет
# (это делает Elo), но по нему отбираются бои для ручной корректировки.
UPSET_GAP = 3

# Elo: ожидаемый результат 1 / (1 + 10^((Rсоперника − Rигрока) / ELO_SCALE)).
# Победитель получает round(K победителя · (1 − ожидаемый)), минимум 1.
# Проигравший теряет round(K проигравшего · (1 − ожидаемый) · доля), минимум 1.
ELO_SCALE = 400
START_POINTS = 1000
# K зависит от опыта: новичок быстрее находит своё место, у опытных таблица спокойнее.
K_NEW = 48
K_EXPERIENCED = 32
NEW_PLAYER_FIGHTS = 10
# Скидка за активность: поражение стоит 75% от полного Elo. Действует на первые
# LOSS_DISCOUNTS_PER_OPPONENT поражения от одного соперника за LOSS_DISCOUNT_WINDOW,
# иначе двое могли бы расти, по очереди проигрывая друг другу.
LOSS_SHARE = 0.75
LOSS_DISCOUNTS_PER_OPPONENT = 2
LOSS_DISCOUNT_WINDOW = timedelta(days=7)
# Пока у игрока меньше боёв, он стоит в таблице ниже всех откалиброванных.
CALIBRATION_FIGHTS = 5
# Простой: через INACTIVITY_GRACE без боя и затем каждые INACTIVITY_STEP игрок теряет
# INACTIVITY_SHARE от превышения над стартовыми очками. Ниже старта не опускает.
INACTIVITY_GRACE = timedelta(days=14)
INACTIVITY_STEP = timedelta(days=7)
INACTIVITY_SHARE = 0.03


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


def expected_score(points: int, opponent_points: int) -> float:
    return 1 / (1 + 10 ** ((opponent_points - points) / ELO_SCALE))


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def k_factor(rated_fights: int) -> int:
    """K по числу боёв, за которые игрок уже получал или терял очки."""
    return K_NEW if rated_fights < NEW_PLAYER_FIGHTS else K_EXPERIENCED


@dataclass(frozen=True)
class FightPoints:
    gain: int
    loss: int
    # На сколько очков меньше проигравший потерял благодаря скидке за активность.
    loss_discount: int


def fight_points(
    winner_points: int, loser_points: int, winner_k: int, loser_k: int, discounted: bool
) -> FightPoints:
    upset_share = 1 - expected_score(winner_points, loser_points)
    gain = max(1, _round(winner_k * upset_share))
    full_loss = max(1, _round(loser_k * upset_share))
    loss = max(1, _round(loser_k * upset_share * LOSS_SHARE)) if discounted else full_loss
    return FightPoints(gain, loss, full_loss - loss)


def is_upset(winner_place: int, loser_place: int) -> bool:
    return winner_place - loser_place >= UPSET_GAP


def _rated_fights(db: Session, player_id: int) -> int:
    return db.scalar(select(func.count()).select_from(RatingChange).where(RatingChange.player_id == player_id))


def _discount_available(db: Session, loser_id: int, winner_id: int, now: datetime) -> bool:
    used = db.scalar(
        select(func.count())
        .select_from(RatingChange)
        .join(Fight, Fight.id == RatingChange.fight_id)
        .where(
            RatingChange.player_id == loser_id,
            RatingChange.loss_discount > 0,
            Fight.winner_id == winner_id,
            Fight.confirmed_at > now - LOSS_DISCOUNT_WINDOW,
        )
    )
    return used < LOSS_DISCOUNTS_PER_OPPONENT


def apply_fight_rating(db: Session, fight: Fight, winner: User, loser: User, now: datetime) -> None:
    places = points_places(db)
    winner_place, loser_place = places[winner.id], places[loser.id]
    result = fight_points(
        winner.rating_points,
        loser.rating_points,
        k_factor(_rated_fights(db, winner.id)),
        k_factor(_rated_fights(db, loser.id)),
        _discount_available(db, loser.id, winner.id, now),
    )
    winner_before, loser_before = winner.rating_points, loser.rating_points
    winner.rating_points += result.gain
    loser.rating_points -= result.loss
    db.flush()
    places_after = points_places(db)
    db.add_all(
        [
            RatingChange(
                fight_id=fight.id,
                player_id=winner.id,
                place_before=winner_place,
                points_before=winner_before,
                delta=result.gain,
                points_after=winner.rating_points,
                place_after=places_after[winner.id],
            ),
            RatingChange(
                fight_id=fight.id,
                player_id=loser.id,
                place_before=loser_place,
                points_before=loser_before,
                delta=-result.loss,
                loss_discount=result.loss_discount,
                points_after=loser.rating_points,
                place_after=places_after[loser.id],
            ),
        ]
    )
    db.flush()


def inactivity_penalty(points: int) -> int:
    """Сколько очков снимается за неделю простоя. Ниже стартовых очков не опускает."""
    excess = points - START_POINTS
    if excess <= 0:
        return 0
    return min(excess, max(1, _round(excess * INACTIVITY_SHARE)))


def _last_fight_times(db: Session) -> dict[int, datetime]:
    last: dict[int, datetime] = {}
    for column in (Fight.winner_id, Fight.loser_id):
        rows = db.execute(
            select(column, func.max(Fight.confirmed_at)).where(Fight.status == FightStatus.CONFIRMED).group_by(column)
        ).all()
        for player_id, moment in rows:
            if player_id not in last or moment > last[player_id]:
                last[player_id] = moment
    return last


def apply_inactivity(db: Session, now: datetime | None = None) -> int:
    """Снимает очки за все наступившие недели простоя. Повторный запуск ничего не меняет.

    Срок каждого снятия считается от последнего боя, поэтому уже снятая неделя узнаётся по due_at.
    Возвращает число снятий.
    """
    now = now or utcnow()
    acquire_rating_lock(db)
    last_fight = _last_fight_times(db)
    applied = 0
    players = db.scalars(
        select(User)
        .where(User.status == UserStatus.ACTIVE, User.rating_points > START_POINTS)
        .order_by(User.id)
        .with_for_update(key_share=True)
    ).all()
    for player in players:
        last = last_fight.get(player.id)
        if last is None:
            continue
        done = set(
            db.scalars(select(RatingDecay.due_at).where(RatingDecay.player_id == player.id, RatingDecay.due_at > last))
        )
        due = last + INACTIVITY_GRACE
        while due <= now:
            penalty = inactivity_penalty(player.rating_points)
            if penalty == 0:
                break
            if due not in done:
                db.add(
                    RatingDecay(
                        player_id=player.id,
                        due_at=due,
                        points_before=player.rating_points,
                        delta=-penalty,
                        points_after=player.rating_points - penalty,
                    )
                )
                player.rating_points -= penalty
                applied += 1
            due += INACTIVITY_STEP
    db.commit()
    return applied


def inactivity_info(db: Session, player: User, now: datetime | None = None) -> dict | None:
    """Для профиля: сколько дней без боя и сколько очков уже снято за этот простой."""
    now = now or utcnow()
    last = _last_fight_times(db).get(player.id)
    if last is None or now - last < INACTIVITY_GRACE - INACTIVITY_STEP:
        return None
    lost = db.scalar(
        select(func.coalesce(func.sum(RatingDecay.delta), 0)).where(
            RatingDecay.player_id == player.id, RatingDecay.due_at > last
        )
    )
    if lost == 0 and player.rating_points <= START_POINTS:
        return None
    return {
        "days_without_fights": (now - last).days,
        "lost_points": -lost,
        "decay_starts_at": last + INACTIVITY_GRACE,
    }


@dataclass
class RatingRow:
    user: User
    points_place: int
    display_place: int | None
    is_special: bool
    is_champion: bool = False
    # Меньше CALIBRATION_FIGHTS боёв: игрок стоит ниже всех откалиброванных.
    is_calibrating: bool = False


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

    Сначала закрепляются спецместа, остальные занимают свободные номера по одному:
    сначала откалиброванные игроки по очкам, затем те, у кого меньше CALIBRATION_FIGHTS боёв.
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
    fights_played = Counter(player_id for winner_id, loser_id, _ in fights for player_id in (winner_id, loser_id))
    free_numbers = (number for number in count(1) if number not in taken_numbers)
    for calibrating in (False, True):
        group = [player for player in to_number if (fights_played[player.id] < CALIBRATION_FIGHTS) == calibrating]
        # Игроки уже идут по убыванию очков, поэтому равные стоят подряд.
        for _, tied in groupby(group, key=lambda player: player.rating_points):
            for player in break_tie(list(tied), fights):
                rows.append(
                    RatingRow(player, points_place_by_id[player.id], next(free_numbers), False, False, calibrating)
                )

    rows.sort(key=lambda row: (not row.is_champion, row.display_place or 0))
    return rows


TablePlace = tuple[int | None, bool]


def table_places(db: Session) -> dict[int, TablePlace]:
    """Номер каждого активного игрока в таблице и признак чемпиона (у чемпиона номера нет)."""
    return {row.user.id: (row.display_place, row.is_champion) for row in rating_table(db)}


def record_table_places(db: Session, fight: Fight, before: dict[int, TablePlace]) -> None:
    """Запоминает в начислениях боя номера в таблице до боя и после всех его последствий."""
    after = table_places(db)
    for change in db.scalars(select(RatingChange).where(RatingChange.fight_id == fight.id)):
        change.table_place_before, change.champion_before = before.get(change.player_id, (None, False))
        change.table_place_after, change.champion_after = after.get(change.player_id, (None, False))
    db.flush()


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
    if row.is_calibrating:
        return "calibration"
    if row.is_champion or row.display_place <= TOP_TIER_LAST_PLACE:
        return "top"
    return "middle" if row.display_place <= MIDDLE_TIER_LAST_PLACE else "bottom"
