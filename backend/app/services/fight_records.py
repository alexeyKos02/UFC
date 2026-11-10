"""Создание записи боя и проверки результата. Общие для обычных, турнирных и титульных боёв."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, not_found
from app.models import Fight, FightConfirmation, FightKind, FightVersion, User, UserStatus
from app.schemas import FightResultIn

FUTURE_TOLERANCE = timedelta(minutes=10)


def ensure_players_active(db: Session, player_ids: list[int]) -> None:
    players = db.scalars(
        select(User).where(User.id.in_(player_ids)).execution_options(populate_existing=True)
    ).all()
    if len(players) != len(set(player_ids)):
        raise not_found("Игрок не найден")
    for player in players:
        if player.status != UserStatus.ACTIVE:
            raise conflict(f"Игрок {player.nickname} заблокирован, бой невозможен")


def validate_result(data: FightResultIn, player1_id: int, player2_id: int) -> None:
    if player1_id == player2_id:
        raise bad_request("Бой возможен только между двумя разными игроками")
    if data.winner_id not in (player1_id, player2_id):
        raise bad_request("Победитель должен быть участником боя")
    if data.fought_at > utcnow() + FUTURE_TOLERANCE:
        raise bad_request("Бой записывается после игры: дата не может быть в будущем")


def apply_version_fields(fight: Fight, data: FightResultIn) -> None:
    fight.fought_at = data.fought_at
    fight.winner_id = data.winner_id
    fight.loser_id = fight.opponent_id(data.winner_id)
    fight.method = data.method
    fight.round_no = data.round


def add_version(db: Session, fight: Fight, actor: User, data: FightResultIn, version_no: int) -> FightVersion:
    """Новая версия сразу несёт подтверждение автора: это смысл кнопки «Отправить и подтвердить»."""
    version = FightVersion(
        fight_id=fight.id,
        version_no=version_no,
        submitted_by_id=actor.id,
        fought_at=data.fought_at,
        winner_id=data.winner_id,
        method=data.method,
        round_no=data.round,
    )
    db.add(version)
    db.flush()
    db.add(FightConfirmation(version_id=version.id, player_id=actor.id))
    return version


def create_fight_record(
    db: Session,
    kind: FightKind,
    actor: User,
    player1_id: int,
    player2_id: int,
    data: FightResultIn,
    client_request_id: str | None = None,
    tournament_match_id: int | None = None,
    title_fight_id: int | None = None,
    planned_fight_id: int | None = None,
) -> Fight:
    validate_result(data, player1_id, player2_id)
    ensure_players_active(db, [player1_id, player2_id])
    fight = Fight(
        kind=kind,
        player1_id=player1_id,
        player2_id=player2_id,
        initiator_id=actor.id,
        client_request_id=client_request_id,
        current_version_no=1,
        tournament_match_id=tournament_match_id,
        title_fight_id=title_fight_id,
        planned_fight_id=planned_fight_id,
    )
    apply_version_fields(fight, data)
    db.add(fight)
    db.flush()
    add_version(db, fight, actor, data, 1)
    db.flush()
    return fight
