from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import Fight, FightKind, FightStatus, TitleFight, TitleFightStatus, User, UserStatus
from app.schemas import FightResultIn, TitleFightIn
from app.services import belts
from app.services.fight_records import create_fight_record
from app.services.rating import acquire_rating_lock

ALREADY_SCHEDULED = "Бой за основной пояс уже назначен. Сначала завершите или отмените его"


def _lock(db: Session, title_fight_id: int) -> TitleFight:
    title_fight = db.scalar(
        select(TitleFight)
        .where(TitleFight.id == title_fight_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if title_fight is None:
        raise not_found("Титульный бой не найден")
    return title_fight


def schedule(db: Session, actor: User, data: TitleFightIn) -> TitleFight:
    acquire_rating_lock(db)
    belt = belts.main_belt(db, lock=True)
    if db.scalar(select(TitleFight.id).where(TitleFight.status == TitleFightStatus.SCHEDULED)):
        raise conflict(ALREADY_SCHEDULED)

    champion_id = belt.current_champion_id
    if champion_id is not None:
        if data.player1_id not in (None, champion_id):
            raise conflict("У пояса есть чемпион: бой назначается между ним и претендентом")
        player1_id = champion_id
    else:
        if data.player1_id is None:
            raise bad_request("Пояс вакантен: выберите двух игроков")
        player1_id = data.player1_id
    player2_id = data.player2_id

    if player1_id == player2_id:
        raise bad_request("Бой возможен только между двумя разными игроками")
    players = db.scalars(select(User).where(User.id.in_([player1_id, player2_id]))).all()
    if len(players) != 2:
        raise not_found("Игрок не найден")
    for player in players:
        if player.status != UserStatus.ACTIVE:
            raise conflict(f"Игрок {player.nickname} заблокирован, назначить бой нельзя")

    title_fight = TitleFight(
        belt_id=belt.id,
        player1_id=player1_id,
        player2_id=player2_id,
        champion_id=champion_id,
        scheduled_at=data.scheduled_at,
        created_by_id=actor.id,
    )
    db.add(title_fight)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict(ALREADY_SCHEDULED) from None
    return title_fight


def cancel(db: Session, actor: User, title_fight_id: int, reason: str | None) -> TitleFight:
    acquire_rating_lock(db)
    title_fight = _lock(db, title_fight_id)
    if title_fight.status == TitleFightStatus.CANCELLED:
        return title_fight
    if title_fight.status == TitleFightStatus.COMPLETED:
        raise conflict("Результат уже подтверждён, отменить назначение нельзя")
    title_fight.status = TitleFightStatus.CANCELLED
    title_fight.cancel_reason = reason
    title_fight.cancelled_by_id = actor.id
    title_fight.cancelled_at = utcnow()
    fight = db.scalar(select(Fight).where(Fight.title_fight_id == title_fight_id))
    if fight is not None and fight.status in (FightStatus.PENDING, FightStatus.DISPUTED):
        fight.status = FightStatus.CANCELLED
    db.commit()
    return title_fight


def submit_result(db: Session, actor: User, title_fight_id: int, data: FightResultIn) -> Fight:
    title_fight = _lock(db, title_fight_id)
    if actor.id not in (title_fight.player1_id, title_fight.player2_id):
        raise forbidden("Результат вносит один из участников боя")
    if title_fight.status != TitleFightStatus.SCHEDULED:
        raise conflict("Назначение закрыто, результат внести нельзя")
    existing = db.scalar(select(Fight).where(Fight.title_fight_id == title_fight_id))
    if existing is not None:
        if existing.initiator_id == actor.id:
            return existing
        raise conflict("Соперник уже внёс результат, откройте запись боя")
    fight = create_fight_record(
        db,
        FightKind.TITLE,
        actor,
        title_fight.player1_id,
        title_fight.player2_id,
        data,
        title_fight_id=title_fight.id,
    )
    db.commit()
    return fight


def on_fight_confirmed(db: Session, fight: Fight) -> None:
    """Вызывается внутри транзакции финального подтверждения."""
    title_fight = _lock(db, fight.title_fight_id)
    if title_fight.status != TitleFightStatus.SCHEDULED:
        raise conflict("Назначение закрыто, подтвердить результат нельзя")
    win = belts.award(db, title_fight.belt_id, fight, title_fight_id=title_fight.id)
    title_fight.status = TitleFightStatus.COMPLETED
    title_fight.winner_id = fight.winner_id
    title_fight.is_defense = win.is_defense
    title_fight.completed_at = utcnow()
    db.flush()
