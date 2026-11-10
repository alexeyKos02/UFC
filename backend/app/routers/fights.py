from fastapi import APIRouter, Query, status
from sqlalchemy import and_, func, or_, select

from app.deps import CurrentUser, Db
from app.errors import forbidden, not_found
from app.models import (
    Fight,
    FightKind,
    FightStatus,
    TitleFight,
    TitleFightStatus,
    Tournament,
    TournamentMatch,
    TournamentStatus,
)
from app.schemas import FightCorrectIn, FightCreateIn, FightDisputeIn, FightVersionRef
from app.serializers import fight_brief, fight_detail, match_out, title_fight_out
from app.services import fights as fight_service

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
            TournamentMatch.winner_id.is_(None),
            Fight.id.is_(None),
        )
        .order_by(TournamentMatch.tournament_id, TournamentMatch.round)
    ).all()

    title_fights = db.scalars(
        select(TitleFight).where(
            and_(
                TitleFight.status == TitleFightStatus.SCHEDULED,
                or_(TitleFight.player1_id == viewer.id, TitleFight.player2_id == viewer.id),
            )
        )
    ).all()

    return {
        "to_confirm": [item for item in briefs if item["can_confirm"]],
        "waiting": [item for item in briefs if item["status"] == "pending" and not item["can_confirm"]],
        "disputed": [item for item in briefs if item["status"] == "disputed"],
        "matches": [match_out(match, viewer) for match in matches],
        "title_fights": [title_fight_out(item, viewer) for item in title_fights],
    }


@router.get("/{fight_id}")
def get_fight(fight_id: int, viewer: CurrentUser, db: Db) -> dict:
    fight = db.get(Fight, fight_id)
    if fight is None:
        raise not_found("Бой не найден")
    if fight.status != FightStatus.CONFIRMED and not (fight.has_player(viewer.id) or viewer.is_staff):
        raise forbidden("Бой ещё не подтверждён, он виден только участникам")
    return fight_detail(fight, viewer)


@router.post("/{fight_id}/confirm")
def confirm_fight(fight_id: int, body: FightVersionRef, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.confirm(db, viewer, fight_id, body.version_no), viewer)


@router.post("/{fight_id}/dispute")
def dispute_fight(fight_id: int, body: FightDisputeIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.dispute(db, viewer, fight_id, body.version_no, body.reason), viewer)


@router.post("/{fight_id}/correct")
def correct_fight(fight_id: int, body: FightCorrectIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(fight_service.correct(db, viewer, fight_id, body), viewer)
