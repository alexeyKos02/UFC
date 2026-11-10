from fastapi import APIRouter, UploadFile
from sqlalchemy import select

from app.deps import CurrentUser, Db
from app.errors import not_found
from app.models import User, UserStatus
from app.schemas import ProfileIn
from app.serializers import (
    account_out,
    fight_brief,
    image_url,
    player_belts,
    player_brief,
    rating_row_out,
    stats_with_leaders,
)
from app.services import accounts, rating, stats, uploads

router = APIRouter(tags=["players"])


@router.get("/players")
def league(viewer: CurrentUser, db: Db, q: str | None = None) -> list[dict]:
    query = (q or "").strip().lower()
    league_stats = stats.league_stats(db)
    result = []
    for row in rating.rating_table(db):
        if query and query not in row.user.nickname.lower():
            continue
        result.append({**rating_row_out(row, viewer), **league_stats.get(row.user.id, stats.EMPTY_STATS)})
    return result


@router.get("/players/options")
def player_options(_: CurrentUser, db: Db) -> list[dict]:
    players = db.scalars(select(User).where(User.status == UserStatus.ACTIVE).order_by(User.nickname))
    return [player_brief(player) for player in players]


@router.get("/players/{player_id}")
def player_profile(player_id: int, viewer: CurrentUser, db: Db) -> dict:
    user = db.get(User, player_id)
    if user is None:
        raise not_found("Игрок не найден")
    row = rating.rating_row_for(db, user)
    return {
        "player": {
            **player_brief(user),
            "full_body_url": image_url(user.full_body_path),
            "created_at": user.created_at,
        },
        "rating": {
            "points": user.rating_points,
            "display_place": row.display_place if row else None,
            "points_place": row.points_place if row and viewer.is_staff else None,
            "is_special": row.is_special if row and viewer.is_staff else False,
            "is_champion": row.is_champion if row else False,
            "tier": rating.rating_tier(row),
        },
        "stats": stats_with_leaders(stats.player_stats(db, user.id)),
        "belts": player_belts(db, user),
        "is_me": viewer.id == user.id,
    }


@router.get("/players/{player_id}/fights")
def player_fights(player_id: int, viewer: CurrentUser, db: Db) -> list[dict]:
    if db.get(User, player_id) is None:
        raise not_found("Игрок не найден")
    fights = stats.confirmed_fights_of(db, player_id)
    return [fight_brief(fight, viewer) for fight in reversed(fights)]


@router.patch("/me/profile")
def update_profile(body: ProfileIn, user: CurrentUser, db: Db) -> dict:
    return account_out(accounts.set_nickname(db, user, body.nickname))


def _replace_image(db, user: User, attribute: str, upload: UploadFile, folder: str) -> dict:
    new_path = uploads.save_image(upload, folder)
    old_path = getattr(user, attribute)
    setattr(user, attribute, new_path)
    db.commit()
    uploads.delete_image(old_path)
    return account_out(user)


@router.post("/me/avatar")
def upload_avatar(file: UploadFile, user: CurrentUser, db: Db) -> dict:
    return _replace_image(db, user, "avatar_path", file, "avatars")


@router.post("/me/full-body")
def upload_full_body(file: UploadFile, user: CurrentUser, db: Db) -> dict:
    return _replace_image(db, user, "full_body_path", file, "full_body")
