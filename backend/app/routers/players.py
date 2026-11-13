from fastapi import APIRouter, UploadFile
from sqlalchemy import case, select
from sqlalchemy.orm import aliased

from app.db import utcnow
from app.deps import CurrentUser, Db
from app.errors import not_found
from app.models import Belt, BeltKind, Fight, FightStatus, RatingChange, TitleFight, User, UserStatus
from app.schemas import ProfileIn
from app.serializers import (
    account_out,
    belt_brief,
    fight_brief,
    image_url,
    player_belts,
    player_brief,
    rating_row_out,
    stats_with_leaders,
)
from app.services import accounts, belts, rating, stats, uploads

router = APIRouter(tags=["players"])


@router.get("/players")
def league(viewer: CurrentUser, db: Db, q: str | None = None) -> list[dict]:
    query = (q or "").strip().lower()
    league_stats = stats.league_stats(db)
    result = []
    for row in rating.rating_table(db):
        if query and query not in row.user.nickname.lower():
            continue
        item = {**rating_row_out(row, viewer), **league_stats.get(row.user.id, stats.EMPTY_STATS)}
        if row.is_champion:
            # Чемпиону нужна «афиша» над таблицей: фото в полный рост и пояс.
            item["player"]["full_body_url"] = image_url(row.user.full_body_path)
            item["belt"] = belt_brief(belts.main_belt(db))
        result.append(item)
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
            "is_calibrating": row.is_calibrating if row else False,
            "inactivity": rating.inactivity_info(db, user) if row else None,
        },
        "stats": stats_with_leaders(stats.player_stats(db, user.id)),
        "belts": player_belts(db, user),
        "is_me": viewer.id == user.id,
        "head_to_head": None if viewer.id == user.id else stats.head_to_head(db, viewer.id, user.id),
    }


@router.get("/players/{player_id}/fights")
def player_fights(player_id: int, viewer: CurrentUser, db: Db) -> list[dict]:
    if db.get(User, player_id) is None:
        raise not_found("Игрок не найден")
    fights = stats.confirmed_fights_of(db, player_id)
    return [fight_brief(fight, viewer) for fight in reversed(fights)]


@router.get("/players/{player_id}/rating-history")
def rating_history(player_id: int, _: CurrentUser, db: Db) -> dict:
    """Очки и номер в таблице после каждого боя игрока, по дате боя — для графиков в профиле."""
    if db.get(User, player_id) is None:
        raise not_found("Игрок не найден")
    opponent = aliased(User)
    rows = db.execute(
        select(RatingChange, Fight, opponent, Belt.kind)
        .join(Fight, Fight.id == RatingChange.fight_id)
        # Титульный бой и его пояс: на графике отмечаются защиты и попытки взять основной пояс.
        .outerjoin(TitleFight, TitleFight.id == Fight.title_fight_id)
        .outerjoin(Belt, Belt.id == TitleFight.belt_id)
        # Соперник — тот из пары, чьё это не начисление.
        .join(
            opponent,
            opponent.id == case((Fight.player1_id == RatingChange.player_id, Fight.player2_id), else_=Fight.player1_id),
        )
        .where(RatingChange.player_id == player_id, Fight.status == FightStatus.CONFIRMED)
        .order_by(Fight.fought_at, Fight.id)
    ).all()
    points = [
        {
            "fight_id": fight.id,
            "kind": fight.kind.value,
            "fought_at": fight.fought_at,
            "confirmed_at": fight.confirmed_at,
            "won": fight.winner_id == player_id,
            "opponent": player_brief(rival),
            "delta": change.delta,
            "points_before": change.points_before,
            "points_after": change.points_after,
            "table_place_before": change.table_place_before,
            "table_place_after": change.table_place_after,
            "champion_before": change.champion_before,
            "champion_after": change.champion_after,
            "main_title_fight": belt_kind == BeltKind.MAIN,
        }
        for change, fight, rival, belt_kind in rows
    ]
    return {"points": points}


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


@router.post("/me/onboarding")
def finish_onboarding(user: CurrentUser, db: Db) -> dict:
    """Отмечает, что знакомство с сайтом пройдено или пропущено. Повторный вызов ничего не меняет."""
    if user.onboarded_at is None:
        user.onboarded_at = utcnow()
        db.commit()
    return account_out(user)


@router.post("/me/avatar")
def upload_avatar(file: UploadFile, user: CurrentUser, db: Db) -> dict:
    return _replace_image(db, user, "avatar_path", file, "avatars")


@router.post("/me/full-body")
def upload_full_body(file: UploadFile, user: CurrentUser, db: Db) -> dict:
    return _replace_image(db, user, "full_body_path", file, "full_body")
