from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found, unauthorized
from app.models import (
    Tournament,
    TournamentParticipant,
    TournamentStatus,
    User,
    UserRole,
    UserSession,
    UserStatus,
)
from app.security import (
    burn_password_check,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.services.rating import acquire_rating_lock

NICKNAME_MAX = 32
BAD_CREDENTIALS = "Неверный логин или пароль"


def _free_nickname(db: Session, base: str) -> str:
    candidate = base
    suffix = 1
    while db.scalar(select(User.id).where(func.lower(User.nickname) == candidate.lower())):
        suffix += 1
        tail = f"_{suffix}"
        candidate = base[: NICKNAME_MAX - len(tail)] + tail
    return candidate


def create_user(
    db: Session, login: str, password: str, role: UserRole = UserRole.PLAYER, nickname: str | None = None
) -> User:
    """Новая строка меняет состав таблицы рейтинга, поэтому вставка идёт под общим замком."""
    password_hash = hash_password(password)
    acquire_rating_lock(db)
    normalized = login.lower()
    if db.scalar(select(User.id).where(User.login == normalized)):
        raise conflict("Такой логин уже занят")
    user = User(
        login=normalized,
        password_hash=password_hash,
        role=role,
        status=UserStatus.ACTIVE,
        nickname=_free_nickname(db, nickname or login),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("Такой логин уже занят") from None
    return user


def open_session(db: Session, user: User) -> str:
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=utcnow() + timedelta(days=settings.session_ttl_days),
        )
    )
    return token


def register(db: Session, login: str, password: str) -> tuple[User, str]:
    user = create_user(db, login, password)
    token = open_session(db, user)
    db.commit()
    return user, token


def login(db: Session, login_value: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.login == login_value.lower()))
    if user is None:
        burn_password_check(password)
        raise unauthorized(BAD_CREDENTIALS)
    if not verify_password(user.password_hash, password):
        raise unauthorized(BAD_CREDENTIALS)
    if user.status != UserStatus.ACTIVE:
        raise forbidden("Учётная запись заблокирована")
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= utcnow()))
    token = open_session(db, user)
    db.commit()
    return user, token


def logout(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_session_token(token)))
    db.commit()


def set_nickname(db: Session, user: User, nickname: str) -> User:
    user.nickname = nickname
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("Такой ник уже занят") from None
    return user


def _lock_user(db: Session, user_id: int) -> User:
    user = db.scalar(
        select(User).where(User.id == user_id).with_for_update(key_share=True).execution_options(populate_existing=True)
    )
    if user is None:
        raise not_found("Игрок не найден")
    return user


def set_role(db: Session, actor: User, user_id: int, role: str) -> User:
    if role not in (UserRole.PLAYER, UserRole.ADMIN):
        raise bad_request("Можно назначить только роль игрока или админа")
    user = _lock_user(db, user_id)
    if user.id == actor.id:
        raise bad_request("Нельзя менять собственную роль")
    if user.role == UserRole.OWNER:
        raise forbidden("Роль владельца меняется только при первоначальной настройке")
    user.role = UserRole(role)
    db.commit()
    return user


def block(db: Session, actor: User, user_id: int) -> User:
    acquire_rating_lock(db)
    user = _lock_user(db, user_id)
    if user.id == actor.id:
        raise bad_request("Нельзя заблокировать самого себя")
    if user.role == UserRole.OWNER:
        raise forbidden("Владельца заблокировать нельзя")
    if user.status == UserStatus.BLOCKED:
        return user
    user.status = UserStatus.BLOCKED
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    # Заявка на ещё не начатый турнир освобождает место, иначе счётчик держал бы недоступного игрока.
    tournament_ids = db.scalars(
        select(Tournament.id)
        .join(TournamentParticipant, TournamentParticipant.tournament_id == Tournament.id)
        .where(TournamentParticipant.user_id == user.id, Tournament.status == TournamentStatus.REGISTRATION)
        .order_by(Tournament.id)
        .with_for_update(of=Tournament)
    ).all()
    if tournament_ids:
        db.execute(
            delete(TournamentParticipant).where(
                TournamentParticipant.user_id == user.id, TournamentParticipant.tournament_id.in_(tournament_ids)
            )
        )
    db.commit()
    return user


def unblock(db: Session, user_id: int) -> User:
    acquire_rating_lock(db)
    user = _lock_user(db, user_id)
    user.status = UserStatus.ACTIVE
    db.commit()
    return user
