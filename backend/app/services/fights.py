"""Жизненный цикл результата: создание, подтверждение, оспаривание, исправление."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import Fight, FightConfirmation, FightKind, FightStatus, User, UserStatus
from app.schemas import FightCorrectIn, FightCreateIn
from app.services import rating, title_fights, tournaments
from app.services.fight_records import (
    add_version,
    apply_version_fields,
    create_fight_record,
    ensure_players_active,
    validate_result,
)

STALE_VERSION = "Результат был изменён. Обновите страницу и проверьте новую версию"


def _lock_fight(db: Session, fight_id: int) -> Fight:
    fight = db.scalar(
        select(Fight).where(Fight.id == fight_id).with_for_update().execution_options(populate_existing=True)
    )
    if fight is None:
        raise not_found("Бой не найден")
    return fight


def _find_by_request(db: Session, actor: User, key: str) -> Fight | None:
    return db.scalar(select(Fight).where(Fight.initiator_id == actor.id, Fight.client_request_id == key))


def create_regular_fight(db: Session, actor: User, data: FightCreateIn) -> Fight:
    key = str(data.client_request_id)
    existing = _find_by_request(db, actor, key)
    if existing is not None:
        return existing
    if data.opponent_id == actor.id:
        raise bad_request("Бой возможен только между двумя разными игроками")
    try:
        fight = create_fight_record(
            db, FightKind.REGULAR, actor, actor.id, data.opponent_id, data, client_request_id=key
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_by_request(db, actor, key)
        if existing is None:
            raise
        return existing
    return fight


def confirm(db: Session, actor: User, fight_id: int, version_no: int) -> Fight:
    # Замок рейтинга берётся первым: второе подтверждение читает места уже под ним.
    rating.acquire_rating_lock(db)
    fight = _lock_fight(db, fight_id)
    if not fight.has_player(actor.id):
        raise forbidden("Подтвердить результат может только участник боя")
    if actor.status != UserStatus.ACTIVE:
        raise forbidden("Учётная запись заблокирована")
    if version_no != fight.current_version_no:
        raise conflict(STALE_VERSION)
    if fight.status == FightStatus.CONFIRMED:
        return fight
    if fight.status != FightStatus.PENDING:
        raise conflict("Этот бой сейчас нельзя подтвердить")

    version = fight.current_version
    confirmed_by = {confirmation.player_id for confirmation in version.confirmations}
    if actor.id in confirmed_by:
        return fight

    ensure_players_active(db, [fight.player1_id, fight.player2_id])
    db.add(FightConfirmation(version_id=version.id, player_id=actor.id))
    confirmed_by.add(actor.id)
    db.flush()
    if confirmed_by == {fight.player1_id, fight.player2_id}:
        _finalize(db, fight)
    db.commit()
    return fight


def _finalize(db: Session, fight: Fight) -> None:
    # Очки по Elo дают все бои, турнирные тоже. Победителю турнира сверху идёт приз турнира.
    now = utcnow()
    players = db.scalars(
        select(User)
        .where(User.id.in_([fight.player1_id, fight.player2_id]))
        .order_by(User.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).all()
    by_id = {player.id: player for player in players}
    rating.apply_fight_rating(db, fight, by_id[fight.winner_id], by_id[fight.loser_id], now)
    fight.status = FightStatus.CONFIRMED
    fight.confirmed_at = now
    db.flush()
    if fight.kind == FightKind.TOURNAMENT:
        tournaments.on_fight_confirmed(db, fight)
    elif fight.kind == FightKind.TITLE:
        title_fights.on_fight_confirmed(db, fight)


def dispute(db: Session, actor: User, fight_id: int, version_no: int, reason: str) -> Fight:
    fight = _lock_fight(db, fight_id)
    if not fight.has_player(actor.id):
        raise forbidden("Оспорить результат может только участник боя")
    if version_no != fight.current_version_no:
        raise conflict(STALE_VERSION)
    version = fight.current_version
    if fight.status == FightStatus.DISPUTED and version.disputed_by_id == actor.id:
        return fight
    if fight.status != FightStatus.PENDING:
        raise conflict("Этот бой сейчас нельзя оспорить")
    if version.submitted_by_id == actor.id:
        raise forbidden("Свою версию результата оспорить нельзя")
    version.dispute_reason = reason
    version.disputed_by_id = actor.id
    version.disputed_at = utcnow()
    fight.status = FightStatus.DISPUTED
    db.commit()
    return fight


def _same_result(fight: Fight, data: FightCorrectIn) -> bool:
    return (
        fight.fought_at == data.fought_at
        and fight.winner_id == data.winner_id
        and fight.method == data.method
        and fight.round_no == data.round
    )


def correct(db: Session, actor: User, fight_id: int, data: FightCorrectIn) -> Fight:
    fight = _lock_fight(db, fight_id)
    if fight.initiator_id != actor.id:
        raise forbidden("Исправить запись может только её инициатор")
    is_replay = (
        fight.status == FightStatus.PENDING
        and fight.current_version_no == data.expected_version + 1
        and _same_result(fight, data)
    )
    if is_replay:
        return fight
    if fight.status != FightStatus.DISPUTED:
        raise conflict("Исправить можно только оспоренную запись")
    if data.expected_version != fight.current_version_no:
        raise conflict(STALE_VERSION)
    validate_result(data, fight.player1_id, fight.player2_id)
    ensure_players_active(db, [fight.player1_id, fight.player2_id])
    new_version_no = fight.current_version_no + 1
    # Старые подтверждения привязаны к прошлой версии и перестают учитываться автоматически.
    add_version(db, fight, actor, data, new_version_no)
    fight.current_version_no = new_version_no
    apply_version_fields(fight, data)
    fight.status = FightStatus.PENDING
    db.commit()
    return fight
