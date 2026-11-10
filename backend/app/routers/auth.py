from fastapi import APIRouter, Request, Response, status

from app.config import settings
from app.deps import CurrentUser, Db
from app.schemas import CredentialsIn, LoginIn
from app.security import COOKIE_NAME
from app.serializers import account_out
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: CredentialsIn, response: Response, db: Db) -> dict:
    user, token = accounts.register(db, body.login, body.password)
    _set_session_cookie(response, token)
    return account_out(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Db) -> dict:
    user, token = accounts.login(db, body.login, body.password)
    _set_session_cookie(response, token)
    return account_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        accounts.logout(db, token)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return account_out(user)
