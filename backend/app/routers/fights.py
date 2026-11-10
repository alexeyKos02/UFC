from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from app.deps import CurrentUser, Db
from app.errors import forbidden, not_found
from app.models import (
    Fight,
    FightKind,
    FightStatus,
    Tournament,
    TournamentMatch,
    TournamentStatus,
)
from app.schemas import (
    FightCorrectIn,
    FightCreateIn,
    FightDisputeIn,
    FightResultIn,
    FightVersionRef,
    PlannedFightIn,
    VoteIn,
)
from app.serializers import fight_brief, fight_detail, match_out, upcoming_out
from app.services import fights as fight_service
from app.services import upcoming as upcoming_service
from app.services.stats import fight_comparison
from app.services.upcoming import UpcomingKind

router = APIRouter(prefix="/fights", tags=["fights"])


@router.get("")
def league_history(
    viewer: CurrentUser,
    db: Db,
    kind: FightKind | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    conditions = [Fight.status == FightStatus.CONFIRMED]
    if kind is not None:
        conditions.append(Fight.kind == kind)
    total = db.scalar(select(func.count()).select_from(Fight).where(*conditions))
    rows = db.scalars(
        select(Fight).where(*conditions).order_by(Fight.fought_at.desc(), Fight.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [fight_brief(fight, viewer) for fight in rows], "total": total}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_fight(body: FightCreateIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.create_regular_fight(db, viewer, body), viewer)


@router.get("/upcoming")
def upcoming_fights(viewer: CurrentUser, db: Db) -> list[dict]:
    return [upcoming_out(kind, target, viewer) for kind, target in upcoming_service.list_upcoming(db)]


@router.put("/upcoming/{kind}/{target_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
def vote(kind: UpcomingKind, target_id: int, body: VoteIn, viewer: CurrentUser, db: Db) -> None:
    upcoming_service.cast_vote(db, viewer, kind, target_id, body.player_id)


@router.post("/planned", status_code=status.HTTP_201_CREATED)
def create_planned_fight(body: PlannedFightIn, viewer: CurrentUser, db: Db) -> dict:
    return upcoming_out("planned", upcoming_service.create_planned_fight(db, viewer, body), viewer)


@router.post("/planned/{planned_id}/result", status_code=status.HTTP_201_CREATED)
def submit_planned_result(planned_id: int, body: FightResultIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(upcoming_service.submit_planned_result(db, viewer, planned_id, body), viewer)


@router.post("/planned/{planned_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_planned_fight(planned_id: int, viewer: CurrentUser, db: Db) -> None:
    upcoming_service.cancel_planned(db, viewer, planned_id)


@router.get("/mine")
def my_fights(viewer: CurrentUser, db: Db) -> dict:
    mine = or_(Fight.player1_id == viewer.id, Fight.player2_id == viewer.id)
    open_fights = db.scalars(
        select(Fight)
        .where(mine, Fight.status.in_([FightStatus.PENDING, FightStatus.DISPUTED]))
        .order_by(Fight.updated_at.desc(), Fight.id.desc())
    ).all()
    briefs = [fight_brief(fight, viewer) for fight in open_fights]

    matches = db.scalars(
        select(TournamentMatch)
        .join(Tournament, Tournament.id == TournamentMatch.tournament_id)
        .outerjoin(Fight, Fight.tournament_match_id == TournamentMatch.id)
        .where(
            Tournament.status == TournamentStatus.IN_PROGRESS,
            or_(TournamentMatch.player1_id == viewer.id, TournamentMatch.player2_id == viewer.id),
            or_(TournamentMatch.player1_id.is_(None), TournamentMatch.player2_id.is_(None)),
            TournamentMatch.winner_id.is_(None),
            Fight.id.is_(None),
        )
        .order_by(TournamentMatch.tournament_id, TournamentMatch.round)
    ).all()

    upcoming = [
        upcoming_out(kind, target, viewer)
        for kind, target in upcoming_service.list_upcoming(db)
        if viewer.id in (target.player1_id, target.player2_id)
    ]

    return {
        "to_confirm": [item for item in briefs if item["can_confirm"]],
        "waiting": [item for item in briefs if item["status"] == "pending" and not item["can_confirm"]],
        "disputed": [item for item in briefs if item["status"] == "disputed"],
        "matches": [match_out(match, viewer) for match in matches],
        "upcoming": upcoming,
    }


@router.get("/{fight_id}")
def get_fight(fight_id: int, viewer: CurrentUser, db: Db) -> dict:
    fight = db.get(Fight, fight_id)
    if fight is None:
        raise not_found("Бой не найден")
    if fight.status != FightStatus.CONFIRMED and not (fight.has_player(viewer.id) or viewer.is_staff):
        raise forbidden("Бой ещё не подтверждён, он виден только участникам")
    return {**fight_detail(fight, viewer), "comparison": fight_comparison(db, fight)}


@router.post("/{fight_id}/confirm")
def confirm_fight(fight_id: int, body: FightVersionRef, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.confirm(db, viewer, fight_id, body.version_no), viewer)


@router.post("/{fight_id}/dispute")
def dispute_fight(fight_id: int, body: FightDisputeIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.dispute(db, viewer, fight_id, body.version_no, body.reason), viewer)


@router.post("/{fight_id}/correct")
def correct_fight(fight_id: int, body: FightCorrectIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.correct(db, viewer, fight_id, body), viewer)
