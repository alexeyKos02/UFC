from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, not_found
from app.models import SpecialPlace, SpecialPlaceAction, SpecialPlaceLog, User, UserStatus
from app.services.rating import acquire_rating_lock


def set_special_place(db: Session, actor: User, user_id: int, place: int) -> SpecialPlace:
    acquire_rating_lock(db)
    user = db.get(User, user_id)
    if user is None:
        raise not_found("Игрок не найден")
    if user.status != UserStatus.ACTIVE:
        raise conflict("Спецместо можно назначить только активному игроку")
    active_count = db.scalar(select(func.count()).select_from(User).where(User.status == UserStatus.ACTIVE))
    if not 1 <= place <= active_count:
        raise bad_request(f"Номер места должен быть от 1 до {active_count}")

    holder = db.scalar(select(SpecialPlace).where(SpecialPlace.place == place))
    if holder is not None and holder.user_id != user_id:
        raise conflict(f"Место №{place} уже закреплено за игроком {holder.user.nickname}")

    current = db.scalar(select(SpecialPlace).where(SpecialPlace.user_id == user_id))
    if current is not None and current.place == place:
        return current

    if current is None:
        current = SpecialPlace(user_id=user_id, place=place, updated_by_id=actor.id)
        db.add(current)
        action, before = SpecialPlaceAction.SET, None
    else:
        action, before = SpecialPlaceAction.CHANGE, current.place
        current.place = place
        current.updated_by_id = actor.id
    db.add(SpecialPlaceLog(user_id=user_id, action=action, place_before=before, place_after=place, actor_id=actor.id))
    db.commit()
    return current


def clear_special_place(db: Session, actor: User, user_id: int) -> None:
    acquire_rating_lock(db)
    current = db.scalar(select(SpecialPlace).where(SpecialPlace.user_id == user_id))
    if current is None:
        return
    db.add(
        SpecialPlaceLog(
            user_id=user_id,
            action=SpecialPlaceAction.CLEAR,
            place_before=current.place,
            place_after=None,
            actor_id=actor.id,
        )
    )
    db.delete(current)
    db.commit()
