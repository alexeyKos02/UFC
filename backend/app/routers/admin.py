from fastapi import APIRouter, Depends, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.deps import Db, OwnerUser, StaffUser, require_staff
from app.errors import not_found
from app.models import (
    Belt,
    BeltKind,
    Fight,
    FightStatus,
    Promo,
    RatingAdjustment,
    RatingAdjustmentLog,
    RatingChange,
    SpecialPlace,
    SpecialPlaceLog,
    TitleFight,
    Tournament,
    User,
)
from app.schemas import (
    AcceptIn,
    AdjustmentCancelIn,
    AdjustmentIn,
    BeltAwardIn,
    BeltIn,
    CancelIn,
    PromoIn,
    PublishIn,
    RoleIn,
    SpecialPlaceIn,
    TitleFightIn,
    TournamentIn,
)
from app.serializers import (
    admin_user_out,
    fight_brief,
    belt_detail,
    belt_out,
    fight_detail,
    player_brief,
    promo_out,
    rating_row_out,
    title_fight_out,
    tournament_cards,
    tournament_detail,
)
from app.services import (
    accounts,
    adjustments,
    belts,
    fight_order,
    promos,
    rating,
    special_places,
    title_fights,
    tournaments,
    uploads,
)
from app.services import fights as fight_service
from app.services.rating import UPSET_GAP

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_staff)])


# Турниры


@router.get("/tournaments")
def admin_tournaments(viewer: StaffUser, db: Db) -> list[dict]:
    rows = db.scalars(select(Tournament).order_by(Tournament.created_at.desc())).all()
    return tournament_cards(db, list(rows), viewer)


@router.post("/tournaments", status_code=status.HTTP_201_CREATED)
def create_tournament(body: TournamentIn, viewer: StaffUser, db: Db) -> dict:
    return tournament_detail(db, tournaments.create_tournament(db, viewer, body), viewer)


@router.patch("/tournaments/{tournament_id}")
def update_tournament(tournament_id: int, body: TournamentIn, viewer: StaffUser, db: Db) -> dict:
    return tournament_detail(db, tournaments.update_tournament(db, tournament_id, body), viewer)


@router.post("/tournaments/{tournament_id}/publish")
def publish_tournament(tournament_id: int, viewer: StaffUser, db: Db) -> dict:
    return tournament_detail(db, tournaments.publish(db, tournament_id), viewer)


@router.post("/tournaments/{tournament_id}/start")
def start_tournament(tournament_id: int, viewer: StaffUser, db: Db) -> dict:
    return tournament_detail(db, tournaments.start(db, tournament_id), viewer)


@router.post("/tournaments/{tournament_id}/cancel")
def cancel_tournament(tournament_id: int, body: CancelIn, viewer: StaffUser, db: Db) -> dict:
    return tournament_detail(db, tournaments.cancel(db, tournament_id, body.reason), viewer)


# Зависшие бои


@router.get("/fights/open")
def admin_open_fights(viewer: StaffUser, db: Db) -> list[dict]:
    """Бои без итога от самых ранних и кого по каждому ждём."""
    fights = db.scalars(
        select(Fight).where(Fight.status.in_(fight_order.OPEN_STATUSES)).order_by(Fight.fought_at, Fight.id)
    ).all()
    waiting = {user.id: user for user in db.scalars(select(User))}
    return [
        {
            **fight_brief(fight, viewer),
            "created_at": fight.created_at,
            "waiting_for": [player_brief(waiting[user_id]) for user_id in fight_order.waiting_for(fight)],
        }
        for fight in fights
    ]


@router.post("/fights/{fight_id}/accept")
def admin_accept_fight(fight_id: int, body: AcceptIn, viewer: StaffUser, db: Db) -> dict:
    return fight_detail(fight_service.admin_accept(db, viewer, fight_id, body.reason), viewer)


@router.post("/fights/{fight_id}/cancel")
def admin_cancel_fight(fight_id: int, body: CancelIn, viewer: StaffUser, db: Db) -> dict:
    return fight_detail(fight_service.admin_cancel(db, viewer, fight_id, body.reason), viewer)


# Пояса


def _belt_or_404(db: Db, belt_id: int) -> Belt:
    belt = db.get(Belt, belt_id)
    if belt is None:
        raise not_found("Пояс не найден")
    return belt


@router.post("/belts", status_code=status.HTTP_201_CREATED)
def create_belt(body: BeltIn, db: Db) -> dict:
    belt = Belt(kind=BeltKind.TOURNAMENT, name=body.name)
    db.add(belt)
    db.commit()
    return belt_out(belt)


@router.patch("/belts/{belt_id}")
def update_belt(belt_id: int, body: BeltIn, db: Db) -> dict:
    belt = _belt_or_404(db, belt_id)
    belt.name = body.name
    db.commit()
    return belt_out(belt)


@router.post("/belts/{belt_id}/award")
def award_belt(belt_id: int, body: BeltAwardIn, actor: StaffUser, db: Db) -> dict:
    return belt_detail(db, belts.award_manually(db, actor, belt_id, body.player_id))


@router.post("/belts/{belt_id}/icon")
def upload_belt_icon(belt_id: int, file: UploadFile, db: Db) -> dict:
    belt = _belt_or_404(db, belt_id)
    new_path = uploads.save_image(file, "belts")
    old_path = belt.icon_path
    belt.icon_path = new_path
    db.commit()
    uploads.delete_image(old_path)
    return belt_out(belt)


# Титульные бои


@router.get("/title-fights")
def admin_title_fights(viewer: StaffUser, db: Db) -> list[dict]:
    rows = db.scalars(select(TitleFight).order_by(TitleFight.created_at.desc(), TitleFight.id.desc())).all()
    return [title_fight_out(row, viewer) for row in rows]


@router.post("/title-fights", status_code=status.HTTP_201_CREATED)
def schedule_title_fight(body: TitleFightIn, viewer: StaffUser, db: Db) -> dict:
    return title_fight_out(title_fights.schedule(db, viewer, body), viewer)


@router.post("/title-fights/{title_fight_id}/cancel")
def cancel_title_fight(title_fight_id: int, body: CancelIn, viewer: StaffUser, db: Db) -> dict:
    return title_fight_out(title_fights.cancel(db, viewer, title_fight_id, body.reason), viewer)


# Рейтинг


@router.get("/rating")
def admin_rating(viewer: StaffUser, db: Db) -> dict:
    rows = rating.rating_table(db)
    specials = db.scalars(select(SpecialPlace).order_by(SpecialPlace.place)).all()
    return {
        "rows": [rating_row_out(row, viewer) for row in rows],
        "active_count": len(rows),
        "special_places": [
            {"place": item.place, "player": player_brief(item.user), "updated_at": item.updated_at}
            for item in specials
        ],
    }


@router.get("/rating/upsets")
def admin_upsets(db: Db) -> list[dict]:
    winner_change = aliased(RatingChange)
    loser_change = aliased(RatingChange)
    rows = db.execute(
        select(Fight, winner_change, loser_change)
        .join(winner_change, (winner_change.fight_id == Fight.id) & (winner_change.player_id == Fight.winner_id))
        .join(loser_change, (loser_change.fight_id == Fight.id) & (loser_change.player_id == Fight.loser_id))
        .where(
            Fight.status == FightStatus.CONFIRMED,
            or_(
                winner_change.place_before - loser_change.place_before >= UPSET_GAP,
                Fight.id.in_(select(RatingAdjustment.fight_id)),
            ),
        )
        .order_by(Fight.fought_at.desc(), Fight.id.desc())
    ).all()
    result = []
    for fight, winner, loser in rows:
        adjustment: RatingAdjustment | None = fight.adjustment
        is_active = adjustment is not None and adjustment.status.value == "active"
        result.append(
            {
                "fight_id": fight.id,
                "fought_at": fight.fought_at,
                "kind": fight.kind.value,
                "winner": player_brief(fight.winner),
                "loser": player_brief(fight.loser),
                "winner_place_before": winner.place_before,
                "loser_place_before": loser.place_before,
                "auto_delta": winner.delta,
                "adjustment": {
                    "winner_delta": adjustment.winner_delta if is_active else 0,
                    "reason": adjustment.reason if is_active else None,
                    "status": adjustment.status.value,
                    "version": adjustment.version,
                }
                if adjustment
                else None,
            }
        )
    return result


@router.put("/rating/adjustments/{fight_id}")
def save_adjustment(fight_id: int, body: AdjustmentIn, viewer: StaffUser, db: Db) -> dict:
    adjustments.save_adjustment(
        db, viewer, fight_id, body.player_id, body.points, body.reason, body.expected_version
    )
    return fight_detail(db.get(Fight, fight_id), viewer)


@router.post("/rating/adjustments/{fight_id}/cancel")
def cancel_adjustment(fight_id: int, body: AdjustmentCancelIn, viewer: StaffUser, db: Db) -> dict:
    adjustments.cancel_adjustment(db, viewer, fight_id, body.reason, body.expected_version)
    return fight_detail(db.get(Fight, fight_id), viewer)


@router.get("/rating/adjustment-log")
def adjustment_log(db: Db, limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    rows = db.scalars(
        select(RatingAdjustmentLog).order_by(RatingAdjustmentLog.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "fight_id": row.fight_id,
            "action": row.action.value,
            "actor": player_brief(row.actor),
            "reason": row.reason,
            "winner": player_brief(row.fight.winner),
            "loser": player_brief(row.fight.loser),
            "winner_delta_before": row.winner_delta_before,
            "winner_delta_after": row.winner_delta_after,
            "winner_points_before": row.winner_points_before,
            "winner_points_after": row.winner_points_after,
            "loser_points_before": row.loser_points_before,
            "loser_points_after": row.loser_points_after,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.put("/rating/special-places/{user_id}")
def set_special_place(user_id: int, body: SpecialPlaceIn, viewer: StaffUser, db: Db) -> dict:
    item = special_places.set_special_place(db, viewer, user_id, body.place)
    return {"user_id": item.user_id, "place": item.place}


@router.delete("/rating/special-places/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_special_place(user_id: int, viewer: StaffUser, db: Db) -> None:
    special_places.clear_special_place(db, viewer, user_id)


@router.get("/rating/special-place-log")
def special_place_log(db: Db, limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    rows = db.scalars(select(SpecialPlaceLog).order_by(SpecialPlaceLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "player": player_brief(row.user),
            "action": row.action.value,
            "place_before": row.place_before,
            "place_after": row.place_after,
            "actor": player_brief(row.actor),
            "created_at": row.created_at,
        }
        for row in rows
    ]


# Промоплашки


@router.get("/promos")
def admin_promos(viewer: StaffUser, db: Db) -> list[dict]:
    rows = db.scalars(select(Promo).order_by(Promo.sort_order, Promo.id)).all()
    return [promo_out(db, row, viewer) for row in rows]


@router.post("/promos", status_code=status.HTTP_201_CREATED)
def create_promo(body: PromoIn, viewer: StaffUser, db: Db) -> dict:
    return promo_out(db, promos.create_promo(db, viewer, body), viewer)


@router.patch("/promos/{promo_id}")
def update_promo(promo_id: int, body: PromoIn, viewer: StaffUser, db: Db) -> dict:
    return promo_out(db, promos.update_promo(db, promo_id, body), viewer)


@router.post("/promos/{promo_id}/publish")
def publish_promo(promo_id: int, body: PublishIn, viewer: StaffUser, db: Db) -> dict:
    return promo_out(db, promos.set_published(db, promo_id, body.published), viewer)


@router.post("/promos/{promo_id}/image")
def upload_promo_image(promo_id: int, file: UploadFile, viewer: StaffUser, db: Db) -> dict:
    promo = promos.get_promo(db, promo_id)
    new_path = uploads.save_image(file, "promos")
    old_path = promo.image_path
    promo.image_path = new_path
    db.commit()
    uploads.delete_image(old_path)
    return promo_out(db, promo, viewer)


# Роли и блокировки: только владелец


@router.get("/users")
def admin_users(_: OwnerUser, db: Db) -> list[dict]:
    specials = {item.user_id: item for item in db.scalars(select(SpecialPlace))}
    users = db.scalars(select(User).order_by(User.nickname)).all()
    return [admin_user_out(user, specials.get(user.id)) for user in users]


@router.post("/users/{user_id}/role")
def set_user_role(user_id: int, body: RoleIn, owner: OwnerUser, db: Db) -> dict:
    return admin_user_out(accounts.set_role(db, owner, user_id, body.role))


@router.post("/users/{user_id}/block")
def block_user(user_id: int, owner: OwnerUser, db: Db) -> dict:
    return admin_user_out(accounts.block(db, owner, user_id))


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: int, _: OwnerUser, db: Db) -> dict:
    return admin_user_out(accounts.unblock(db, user_id))
