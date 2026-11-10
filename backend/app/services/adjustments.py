"""Ручная корректировка за исключительный апсет."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, not_found
from app.models import (
    AdjustmentAction,
    AdjustmentStatus,
    Fight,
    FightStatus,
    RatingAdjustment,
    RatingAdjustmentLog,
    RatingChange,
    User,
)
from app.services.rating import acquire_rating_lock, is_upset


def _lock_row(db: Session, stmt):
    return db.scalar(stmt.with_for_update().execution_options(populate_existing=True))


def _load_upset_fight(db: Session, fight_id: int) -> Fight:
    fight = db.get(Fight, fight_id)
    if fight is None:
        raise not_found("Бой не найден")
    if fight.status != FightStatus.CONFIRMED:
        raise conflict("Корректировать можно только подтверждённый бой")
    changes = {
        change.player_id: change
        for change in db.scalars(select(RatingChange).where(RatingChange.fight_id == fight.id))
    }
    if not is_upset(changes[fight.winner_id].place_before, changes[fight.loser_id].place_before):
        raise conflict("Победитель не был ниже соперника на 3 места или больше")
    return fight


def _lock_players(db: Session, fight: Fight) -> tuple[User, User]:
    rows = db.scalars(
        select(User)
        .where(User.id.in_([fight.winner_id, fight.loser_id]))
        .order_by(User.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).all()
    by_id = {user.id: user for user in rows}
    return by_id[fight.winner_id], by_id[fight.loser_id]


def _apply(
    db: Session,
    fight: Fight,
    actor: User,
    action: AdjustmentAction,
    reason: str,
    before: int,
    after: int,
) -> None:
    winner, loser = _lock_players(db, fight)
    diff = after - before
    log = RatingAdjustmentLog(
        fight_id=fight.id,
        action=action,
        actor_id=actor.id,
        reason=reason,
        winner_delta_before=before,
        winner_delta_after=after,
        winner_points_before=winner.rating_points,
        winner_points_after=winner.rating_points + diff,
        loser_points_before=loser.rating_points,
        loser_points_after=loser.rating_points - diff,
    )
    winner.rating_points += diff
    loser.rating_points -= diff
    db.add(log)


def save_adjustment(
    db: Session, actor: User, fight_id: int, player_id: int, points: int, reason: str, expected_version: int
) -> RatingAdjustment:
    acquire_rating_lock(db)
    fight = _load_upset_fight(db, fight_id)
    if player_id not in (fight.winner_id, fight.loser_id):
        raise bad_request("Выберите участника этого боя")
    if points == 0:
        raise bad_request("Укажите ненулевое число очков")
    new_delta = points if player_id == fight.winner_id else -points

    adjustment = _lock_row(db, select(RatingAdjustment).where(RatingAdjustment.fight_id == fight_id))
    current_version = adjustment.version if adjustment else 0
    is_active = adjustment is not None and adjustment.status == AdjustmentStatus.ACTIVE

    is_replay = (
        is_active
        and adjustment.winner_delta == new_delta
        and adjustment.reason == reason
        and expected_version == current_version - 1
    )
    if is_replay:
        return adjustment
    if expected_version != current_version:
        raise conflict("Корректировку уже изменили. Обновите страницу и повторите действие")

    before = adjustment.winner_delta if is_active else 0
    if adjustment is None:
        adjustment = RatingAdjustment(
            fight_id=fight_id,
            status=AdjustmentStatus.ACTIVE,
            winner_delta=new_delta,
            reason=reason,
            version=1,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        db.add(adjustment)
    else:
        adjustment.status = AdjustmentStatus.ACTIVE
        adjustment.winner_delta = new_delta
        adjustment.reason = reason
        adjustment.version = current_version + 1
        adjustment.updated_by_id = actor.id

    action = AdjustmentAction.UPDATE if is_active else AdjustmentAction.CREATE
    _apply(db, fight, actor, action, reason, before, new_delta)
    db.commit()
    return adjustment


def cancel_adjustment(
    db: Session, actor: User, fight_id: int, reason: str, expected_version: int
) -> RatingAdjustment:
    acquire_rating_lock(db)
    adjustment = _lock_row(db, select(RatingAdjustment).where(RatingAdjustment.fight_id == fight_id))
    if adjustment is None:
        raise not_found("Корректировка не найдена")
    if adjustment.status == AdjustmentStatus.CANCELLED:
        return adjustment
    if adjustment.version != expected_version:
        raise conflict("Корректировку уже изменили. Обновите страницу и повторите действие")

    fight = db.get(Fight, fight_id)
    before = adjustment.winner_delta
    _apply(db, fight, actor, AdjustmentAction.CANCEL, reason, before, 0)
    adjustment.status = AdjustmentStatus.CANCELLED
    adjustment.winner_delta = 0
    adjustment.reason = reason
    adjustment.version += 1
    adjustment.updated_by_id = actor.id
    db.commit()
    return adjustment
