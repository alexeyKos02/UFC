from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, Db
from app.errors import not_found
from app.models import Tournament, TournamentStatus
from app.schemas import FightResultIn
from app.serializers import fight_detail, tournament_cards, tournament_detail
from app.services import tournaments as service

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def visible_to(viewer) -> list:
    return [] if viewer.is_staff else [Tournament.status != TournamentStatus.DRAFT]


@router.get("")
def list_tournaments(viewer: CurrentUser, db: Db) -> list[dict]:
    rows = db.scalars(
        select(Tournament).where(Tournament.status != TournamentStatus.DRAFT).order_by(Tournament.created_at.desc())
    ).all()
    return tournament_cards(db, list(rows), viewer)


@router.get("/{tournament_id}")
def get_tournament(tournament_id: int, viewer: CurrentUser, db: Db) -> dict:
    tournament = db.scalar(select(Tournament).where(Tournament.id == tournament_id, *visible_to(viewer)))
    if tournament is None:
        raise not_found("Турнир не найден")
    return tournament_detail(db, tournament, viewer)


@router.post("/{tournament_id}/join")
def join(tournament_id: int, viewer: CurrentUser, db: Db) -> dict:
    return tournament_detail(db, service.join(db, viewer, tournament_id), viewer)


@router.post("/{tournament_id}/leave")
def leave(tournament_id: int, viewer: CurrentUser, db: Db) -> dict:
    return tournament_detail(db, service.leave(db, viewer, tournament_id), viewer)


@router.post("/matches/{match_id}/result", status_code=201)
def submit_match_result(match_id: int, body: FightResultIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(service.submit_match_result(db, viewer, match_id, body), viewer)
