from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, Db
from app.errors import not_found
from app.models import Belt, BeltKind, TitleFight, Tournament, TournamentStatus
from app.schemas import FightResultIn
from app.serializers import belt_detail, belt_out, fight_detail, promo_out, title_fight_out, tournament_cards
from app.services import promos, title_fights

router = APIRouter(tags=["public"])


@router.get("/home")
def home(viewer: CurrentUser, db: Db) -> dict:
    tournaments = db.scalars(
        select(Tournament)
        .where(Tournament.status.in_([TournamentStatus.REGISTRATION, TournamentStatus.IN_PROGRESS]))
        .order_by(Tournament.status, Tournament.created_at.desc())
    ).all()
    return {
        "tournaments": tournament_cards(db, list(tournaments), viewer),
        "promos": [promo_out(db, promo, viewer) for promo in promos.visible_promos(db)],
    }


@router.get("/belts")
def list_belts(_: CurrentUser, db: Db) -> list[dict]:
    belts = db.scalars(select(Belt).order_by(Belt.kind != BeltKind.MAIN, Belt.name)).all()
    return [belt_out(belt) for belt in belts]


@router.get("/belts/{belt_id}")
def get_belt(belt_id: int, _: CurrentUser, db: Db) -> dict:
    belt = db.get(Belt, belt_id)
    if belt is None:
        raise not_found("Пояс не найден")
    return belt_detail(db, belt)


@router.get("/title-fights/{title_fight_id}")
def get_title_fight(title_fight_id: int, viewer: CurrentUser, db: Db) -> dict:
    title_fight = db.get(TitleFight, title_fight_id)
    if title_fight is None:
        raise not_found("Титульный бой не найден")
    return title_fight_out(title_fight, viewer)


@router.post("/title-fights/{title_fight_id}/result", status_code=201)
def submit_title_result(title_fight_id: int, body: FightResultIn, viewer: CurrentUser, db: Db) -> dict:
    return fight_detail(title_fights.submit_result(db, viewer, title_fight_id, body), viewer)
