from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.errors import forbidden, unauthorized
from app.models import User, UserRole, UserSession, UserStatus
from app.security import COOKIE_NAME, hash_session_token

Db = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise unauthorized()
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token), UserSession.expires_at > utcnow()
        )
    )
    if session is None:
        raise unauthorized("Сессия истекла, войдите снова")
    if session.user.status != UserStatus.ACTIVE:
        raise forbidden("Учётная запись заблокирована")
    return session.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_staff(user: CurrentUser) -> User:
    if not user.is_staff:
        raise forbidden("Действие доступно только администратору или владельцу")
    return user


def require_owner(user: CurrentUser) -> User:
    if user.role != UserRole.OWNER:
        raise forbidden("Действие доступно только владельцу")
    return user


StaffUser = Annotated[User, Depends(require_staff)]
OwnerUser = Annotated[User, Depends(require_owner)]
