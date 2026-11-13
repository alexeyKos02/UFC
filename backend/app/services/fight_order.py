"""Порядок боёв: очки считаются в порядке подтверждения, поэтому он обязан совпадать с порядком боёв.

Правила:
- бой нельзя подтвердить, пока у кого-то из его участников есть более ранний бой без итога
  (ждёт подтверждения или оспорен); «раньше» — по дате боя, при равной дате — по номеру записи;
- бой нельзя записать (или исправить) с датой раньше последнего подтверждённого боя его участников.
Зависший бой админ засчитывает или отменяет (app/services/fights.py).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict
from app.models import Fight, FightStatus, User

OPEN_STATUSES = (FightStatus.PENDING, FightStatus.DISPUTED)
MSK = timezone(timedelta(hours=3))


def _when(moment: datetime) -> str:
    return moment.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


def _with_player(player_ids: list[int]):
    return or_(Fight.player1_id.in_(player_ids), Fight.player2_id.in_(player_ids))


def _earlier_than(fight: Fight):
    return or_(
        Fight.fought_at < fight.fought_at,
        and_(Fight.fought_at == fight.fought_at, Fight.id < fight.id),
    )


def earliest_blocker(db: Session, fight: Fight) -> Fight | None:
    """Самый ранний бой без итога у участников этого боя, который идёт раньше него."""
    return db.scalar(
        select(Fight)
        .where(
            Fight.id != fight.id,
            Fight.status.in_(OPEN_STATUSES),
            _with_player([fight.player1_id, fight.player2_id]),
            _earlier_than(fight),
        )
        .order_by(Fight.fought_at, Fight.id)
        .limit(1)
    )


def waiting_for(fight: Fight) -> list[int]:
    """Кто должен сделать следующий шаг по бою без итога."""
    if fight.status == FightStatus.DISPUTED:
        return [fight.initiator_id]
    confirmed = {item.player_id for item in fight.current_version.confirmations}
    return [player_id for player_id in (fight.player1_id, fight.player2_id) if player_id not in confirmed]


def _names(db: Session, user_ids: list[int]) -> str:
    users = db.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.nickname)).all()
    return ", ".join(user.nickname for user in users)


def blocker_text(db: Session, blocker: Fight) -> str:
    return (
        f"Сначала должен получить итог более ранний бой {blocker.player1.nickname} — "
        f"{blocker.player2.nickname} от {_when(blocker.fought_at)} (бой #{blocker.id}). "
        f"Ждём: {_names(db, waiting_for(blocker))}"
    )


def ensure_in_order(db: Session, fight: Fight) -> None:
    blocker = earliest_blocker(db, fight)
    if blocker is not None:
        raise conflict(blocker_text(db, blocker))


def latest_confirmed(
    db: Session, player_ids: list[int], exclude_fight_id: int | None = None
) -> tuple[User, datetime] | None:
    """Самый поздний подтверждённый бой среди участников: (игрок, дата боя)."""
    found: tuple[User, datetime] | None = None
    for player_id in player_ids:
        stmt = select(func.max(Fight.fought_at)).where(
            Fight.status == FightStatus.CONFIRMED, _with_player([player_id])
        )
        if exclude_fight_id is not None:
            stmt = stmt.where(Fight.id != exclude_fight_id)
        latest = db.scalar(stmt)
        if latest is not None and (found is None or latest > found[1]):
            found = (db.get(User, player_id), latest)
    return found


def ensure_not_backdated(
    db: Session, player_ids: list[int], fought_at: datetime, exclude_fight_id: int | None = None
) -> None:
    """Новая дата не раньше последнего подтверждённого боя любого из участников."""
    latest = latest_confirmed(db, player_ids, exclude_fight_id)
    if latest is not None and fought_at < latest[1]:
        player, moment = latest
        raise bad_request(
            f"Бои задним числом записывать нельзя: у игрока {player.nickname} уже подтверждён бой "
            f"от {_when(moment)}. Укажите дату не раньше этой"
        )


def backdated_info(db: Session, fight: Fight) -> dict | None:
    """Бой без итога, сыгранный раньше уже подтверждённого боя участника: подтвердить его нельзя."""
    if fight.status not in OPEN_STATUSES:
        return None
    latest = latest_confirmed(db, [fight.player1_id, fight.player2_id], fight.id)
    if latest is None or fight.fought_at >= latest[1]:
        return None
    return {"player": latest[0], "latest_fought_at": latest[1]}


def ensure_confirmable_date(db: Session, fight: Fight) -> None:
    info = backdated_info(db, fight)
    if info is not None:
        raise conflict(
            f"Этот бой сыгран раньше уже подтверждённого боя игрока {info['player'].nickname} "
            f"(от {_when(info['latest_fought_at'])}), подтвердить или засчитать его нельзя: очки считаются "
            "по порядку. Исправьте дату через «Оспорить» или попросите администратора отменить бой"
        )


def blocked_info(db: Session, fight: Fight) -> dict | None:
    """Для карточки боя без итога: какой бой его держит и кого ждём."""
    if fight.status not in OPEN_STATUSES:
        return None
    blocker = earliest_blocker(db, fight)
    if blocker is None:
        return None
    waiting = db.scalars(select(User).where(User.id.in_(waiting_for(blocker))).order_by(User.nickname)).all()
    return {"fight": blocker, "waiting_for": list(waiting)}


def blocking_report(db: Session, viewer: User) -> list[dict]:
    """Бои без итога, где следующий шаг за зрителем и из-за которых стоят более поздние бои."""
    mine = db.scalars(
        select(Fight)
        .where(Fight.status.in_(OPEN_STATUSES), _with_player([viewer.id]))
        .order_by(Fight.fought_at, Fight.id)
    ).all()
    report = []
    for fight in mine:
        if viewer.id not in waiting_for(fight):
            continue
        later = db.scalars(
            select(Fight)
            .where(
                Fight.id != fight.id,
                Fight.status.in_(OPEN_STATUSES),
                _with_player([fight.player1_id, fight.player2_id]),
                or_(
                    Fight.fought_at > fight.fought_at,
                    and_(Fight.fought_at == fight.fought_at, Fight.id > fight.id),
                ),
            )
            .order_by(Fight.fought_at, Fight.id)
        ).all()
        if not later:
            continue
        delayed_ids = sorted(
            {player_id for item in later for player_id in (item.player1_id, item.player2_id)} - {viewer.id}
        )
        delayed = db.scalars(select(User).where(User.id.in_(delayed_ids)).order_by(User.nickname)).all()
        report.append({"fight": fight, "delayed_players": list(delayed), "delayed_fights": len(later)})
    return report


def blocks_count(db: Session, fight: Fight) -> int:
    """Сколько боёв без итога стоят из-за этого боя (у тех же игроков и позже него)."""
    return db.scalar(
        select(func.count())
        .select_from(Fight)
        .where(
            Fight.id != fight.id,
            Fight.status.in_(OPEN_STATUSES),
            _with_player([fight.player1_id, fight.player2_id]),
            or_(
                Fight.fought_at > fight.fought_at,
                and_(Fight.fought_at == fight.fought_at, Fight.id > fight.id),
            ),
        )
    )
