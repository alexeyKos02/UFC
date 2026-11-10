"""Бои до внесения результата: запланированные игроками, титульные, матчи турниров. Голосование зрителей."""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Fight,
    FightKind,
    FightVote,
    PlannedFight,
    PlannedFightStatus,
    TitleFight,
    TitleFightStatus,
    Tournament,
    TournamentMatch,
    TournamentStatus,
    User,
)
from app.schemas import FightResultIn, PlannedFightIn
from app.services.fight_records import create_fight_record, ensure_players_active

UpcomingKind = Literal["planned", "title", "tournament"]
Target = PlannedFight | TitleFight | TournamentMatch

_MODELS = {"planned": PlannedFight, "title": TitleFight, "tournament": TournamentMatch}
_VOTE_COLUMNS = {
    "planned": FightVote.planned_fight_id,
    "title": FightVote.title_fight_id,
    "tournament": FightVote.tournament_match_id,
}


def _find_by_request(db: Session, actor: User, key: str) -> PlannedFight | None:
    return db.scalar(
        select(PlannedFight).where(PlannedFight.created_by_id == actor.id, PlannedFight.client_request_id == key)
    )


def create_planned_fight(db: Session, actor: User, data: PlannedFightIn) -> PlannedFight:
    key = str(data.client_request_id)
    existing = _find_by_request(db, actor, key)
    if existing is not None:
        return existing
    if data.opponent_id == actor.id:
        raise bad_request("Бой возможен только между двумя разными игроками")
    if data.scheduled_at <= utcnow():
        raise bad_request("Дата запланированного боя должна быть в будущем")
    ensure_players_active(db, [actor.id, data.opponent_id])
    planned = PlannedFight(
        player1_id=actor.id,
        player2_id=data.opponent_id,
        scheduled_at=data.scheduled_at,
        created_by_id=actor.id,
        client_request_id=key,
    )
    db.add(planned)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_by_request(db, actor, key)
        if existing is None:
            raise
        return existing
    return planned


def _lock_planned(db: Session, planned_id: int) -> PlannedFight:
    planned = db.scalar(
        select(PlannedFight)
        .where(PlannedFight.id == planned_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if planned is None:
        raise not_found("Запланированный бой не найден")
    return planned


def submit_planned_result(db: Session, actor: User, planned_id: int, data: FightResultIn) -> Fight:
    planned = _lock_planned(db, planned_id)
    if actor.id not in (planned.player1_id, planned.player2_id):
        raise forbidden("Результат вносит один из участников боя")
    if planned.status != PlannedFightStatus.SCHEDULED:
        raise conflict("Бой отменён, результат внести нельзя")
    existing = db.scalar(select(Fight).where(Fight.planned_fight_id == planned_id))
    if existing is not None:
        if existing.initiator_id == actor.id:
            return existing
        raise conflict("Соперник уже внёс результат, откройте запись боя")
    fight = create_fight_record(
        db,
        FightKind.REGULAR,
        actor,
        planned.player1_id,
        planned.player2_id,
        data,
        planned_fight_id=planned.id,
    )
    db.commit()
    return fight


def cancel_planned(db: Session, actor: User, planned_id: int) -> PlannedFight:
    planned = _lock_planned(db, planned_id)
    if actor.id not in (planned.player1_id, planned.player2_id) and not actor.is_staff:
        raise forbidden("Отменить бой может его участник, админ или владелец")
    if planned.status == PlannedFightStatus.CANCELLED:
        return planned
    if db.scalar(select(Fight.id).where(Fight.planned_fight_id == planned_id)) is not None:
        raise conflict("Результат уже внесён, отменить бой нельзя")
    planned.status = PlannedFightStatus.CANCELLED
    planned.cancelled_by_id = actor.id
    planned.cancelled_at = utcnow()
    db.commit()
    return planned


def list_upcoming(db: Session) -> list[tuple[UpcomingKind, Target]]:
    """Бои с известной парой, по которым ещё не внесён результат. Сначала ближайшие по дате."""
    planned = db.scalars(
        select(PlannedFight)
        .outerjoin(Fight, Fight.planned_fight_id == PlannedFight.id)
        .where(PlannedFight.status == PlannedFightStatus.SCHEDULED, Fight.id.is_(None))
    ).all()
    title_fights = db.scalars(
        select(TitleFight)
        .outerjoin(Fight, Fight.title_fight_id == TitleFight.id)
        .where(TitleFight.status == TitleFightStatus.SCHEDULED, Fight.id.is_(None))
    ).all()
    matches = db.scalars(
        select(TournamentMatch)
        .join(Tournament, Tournament.id == TournamentMatch.tournament_id)
        .outerjoin(Fight, Fight.tournament_match_id == TournamentMatch.id)
        .where(
            Tournament.status == TournamentStatus.IN_PROGRESS,
            TournamentMatch.is_bye.is_(False),
            TournamentMatch.winner_id.is_(None),
            TournamentMatch.player1_id.is_not(None),
            TournamentMatch.player2_id.is_not(None),
            Fight.id.is_(None),
        )
    ).all()
    items: list[tuple[UpcomingKind, Target]] = [
        *(("planned", item) for item in planned),
        *(("title", item) for item in title_fights),
        *(("tournament", item) for item in matches),
    ]

    def order(item: tuple[UpcomingKind, Target]) -> tuple:
        scheduled_at = getattr(item[1], "scheduled_at", None)
        return (scheduled_at is None, scheduled_at, item[1].id)

    return sorted(items, key=order)


def _is_open_for_votes(kind: UpcomingKind, target: Target) -> bool:
    if target.fight is not None:
        return False
    if kind == "planned":
        return target.status == PlannedFightStatus.SCHEDULED
    if kind == "title":
        return target.status == TitleFightStatus.SCHEDULED
    return (
        target.tournament.status == TournamentStatus.IN_PROGRESS
        and not target.is_bye
        and target.winner_id is None
        and target.player1_id is not None
        and target.player2_id is not None
    )


def cast_vote(db: Session, actor: User, kind: UpcomingKind, target_id: int, player_id: int) -> None:
    model = _MODELS[kind]
    # Замок на бой не даёт двум одновременным запросам одного зрителя создать две строки.
    target = db.scalar(
        select(model).where(model.id == target_id).with_for_update().execution_options(populate_existing=True)
    )
    if target is None:
        raise not_found("Бой не найден")
    if not _is_open_for_votes(kind, target):
        raise conflict("Голосование за этот бой закрыто")
    if actor.id in (target.player1_id, target.player2_id):
        raise forbidden("Участники боя не голосуют")
    if player_id not in (target.player1_id, target.player2_id):
        raise bad_request("Голосовать можно только за участника этого боя")

    column = _VOTE_COLUMNS[kind]
    vote = db.scalar(select(FightVote).where(FightVote.voter_id == actor.id, column == target_id))
    if vote is None:
        db.add(FightVote(voter_id=actor.id, voted_for_id=player_id, **{column.key: target_id}))
    else:
        vote.voted_for_id = player_id
    db.commit()
