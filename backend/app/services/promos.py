from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, not_found
from app.models import Promo, PromoType, Tournament, TournamentStatus, User
from app.schemas import PromoIn


def _validate(db: Session, data: PromoIn) -> None:
    if data.show_from and data.show_until and data.show_until <= data.show_from:
        raise bad_request("Окончание показа должно быть позже начала")
    if data.type == PromoType.TOURNAMENT:
        if data.tournament_id is None:
            raise bad_request("Выберите турнир")
        if db.get(Tournament, data.tournament_id) is None:
            raise not_found("Турнир не найден")
    elif data.type == PromoType.FIGHT_ANNOUNCEMENT:
        if data.fighter1_id is None or data.fighter2_id is None:
            raise bad_request("Выберите двух участников анонса")
        if data.fighter1_id == data.fighter2_id:
            raise bad_request("Участники анонса должны быть разными")
        _ensure_users(db, [data.fighter1_id, data.fighter2_id])
    else:
        if data.player_id is None:
            raise bad_request("Выберите бойца недели")
        if data.show_from is None or data.show_until is None:
            raise bad_request("Для бойца недели задайте период показа")
        _ensure_users(db, [data.player_id])


def _ensure_users(db: Session, ids: list[int]) -> None:
    found = db.scalars(select(User.id).where(User.id.in_(ids))).all()
    if len(found) != len(set(ids)):
        raise not_found("Игрок не найден")


def _apply(promo: Promo, data: PromoIn) -> None:
    promo.type = data.type
    promo.title = data.title
    promo.description = data.description
    promo.show_from = data.show_from
    promo.show_until = data.show_until
    promo.sort_order = data.sort_order
    # Поля чужого типа обнуляются, чтобы при смене типа не оставались висячие ссылки.
    promo.tournament_id = data.tournament_id if data.type == PromoType.TOURNAMENT else None
    is_announcement = data.type == PromoType.FIGHT_ANNOUNCEMENT
    promo.fighter1_id = data.fighter1_id if is_announcement else None
    promo.fighter2_id = data.fighter2_id if is_announcement else None
    promo.fight_at = data.fight_at if is_announcement else None
    promo.player_id = data.player_id if data.type == PromoType.FIGHTER_OF_WEEK else None


def create_promo(db: Session, actor: User, data: PromoIn) -> Promo:
    _validate(db, data)
    promo = Promo(created_by_id=actor.id, is_published=False)
    _apply(promo, data)
    db.add(promo)
    db.commit()
    return promo


def get_promo(db: Session, promo_id: int) -> Promo:
    promo = db.get(Promo, promo_id)
    if promo is None:
        raise not_found("Промоплашка не найдена")
    return promo


def update_promo(db: Session, promo_id: int, data: PromoIn) -> Promo:
    promo = get_promo(db, promo_id)
    _validate(db, data)
    _apply(promo, data)
    db.commit()
    return promo


def set_published(db: Session, promo_id: int, published: bool) -> Promo:
    promo = get_promo(db, promo_id)
    promo.is_published = published
    db.commit()
    return promo


def visible_promos(db: Session) -> list[Promo]:
    now = utcnow()
    return list(
        db.scalars(
            select(Promo)
            .outerjoin(Tournament, Promo.tournament_id == Tournament.id)
            .where(
                Promo.is_published.is_(True),
                or_(Promo.show_from.is_(None), Promo.show_from <= now),
                or_(Promo.show_until.is_(None), Promo.show_until >= now),
                or_(Promo.tournament_id.is_(None), Tournament.status != TournamentStatus.DRAFT),
            )
            .order_by(Promo.sort_order, Promo.id)
        )
    )
