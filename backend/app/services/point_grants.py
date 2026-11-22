"""Очки, которые админ или владелец начисляет или снимает игроку вручную, с причиной.

Начисление — событие пересчёта по дате (created_at): очки игрока и номер в таблице до и после
пишет пересчёт. Отмена убирает событие и пересчитывает историю с его даты.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, not_found
from app.models import AdjustmentStatus, PointGrant, User, UserStatus
from app.services import recalc
from app.services.rating import acquire_rating_lock


def _replay_from(db: Session, grant: PointGrant) -> None:
    db.flush()
    recalc.recalculate(db.connection(), (grant.created_at, 0))
    db.commit()
    db.expire_all()


def create_grant(db: Session, actor: User, player_id: int, delta: int, reason: str) -> PointGrant:
    acquire_rating_lock(db)
    if delta == 0:
        raise bad_request("Укажите ненулевое число очков")
    player = db.get(User, player_id)
    if player is None:
        raise not_found("Игрок не найден")
    if player.status != UserStatus.ACTIVE:
        raise conflict(f"Игрок {player.nickname} заблокирован, начислить очки нельзя")
    grant = PointGrant(
        player_id=player.id,
        delta=delta,
        reason=reason,
        status=AdjustmentStatus.ACTIVE,
        created_by_id=actor.id,
        created_at=utcnow(),
    )
    db.add(grant)
    _replay_from(db, grant)
    return db.get(PointGrant, grant.id)


def cancel_grant(db: Session, actor: User, grant_id: int, reason: str) -> PointGrant:
    acquire_rating_lock(db)
    grant = db.scalar(
        select(PointGrant)
        .where(PointGrant.id == grant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if grant is None:
        raise not_found("Начисление не найдено")
    if grant.status == AdjustmentStatus.CANCELLED:
        return grant
    grant.status = AdjustmentStatus.CANCELLED
    grant.cancelled_by_id = actor.id
    grant.cancelled_at = utcnow()
    grant.cancel_reason = reason
    _replay_from(db, grant)
    return db.get(PointGrant, grant_id)
