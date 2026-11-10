from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.errors import AppError
from app.routers import admin, auth, fights, players, public, tournaments

app = FastAPI(title="Лига игроков UFC", docs_url="/api/docs", openapi_url="/api/openapi.json")

FIELD_LABELS = {
    "login": "Логин",
    "password": "Пароль",
    "nickname": "Ник",
    "reason": "Причина",
    "title": "Название",
    "name": "Название",
    "description": "Описание",
    "capacity": "Лимит участников",
    "fought_at": "Дата боя",
    "winner_id": "Победитель",
    "opponent_id": "Соперник",
    "round": "Раунд",
    "points": "Очки",
    "place": "Номер места",
}


def _humanize(error: dict) -> str:
    field = str(error["loc"][-1]) if error.get("loc") else ""
    label = FIELD_LABELS.get(field, field)
    context = error.get("ctx") or {}
    match error.get("type"):
        case "missing":
            return f"{label}: обязательное поле"
        case "string_too_short":
            return f"{label}: минимум символов — {context.get('min_length')}"
        case "string_too_long":
            return f"{label}: максимум символов — {context.get('max_length')}"
        case "string_pattern_mismatch":
            return f"{label}: допустимы латинские буквы, цифры и символы _ . -"
        case "greater_than_equal":
            return f"{label}: значение не меньше {context.get('ge')}"
        case "less_than_equal":
            return f"{label}: значение не больше {context.get('le')}"
        case _:
            return f"{label}: некорректное значение"


@app.exception_handler(AppError)
def handle_app_error(_: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(RequestValidationError)
def handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "; ".join(_humanize(item) for item in error.errors())},
    )


api = APIRouter(prefix="/api")
for module in (auth, players, fights, tournaments, public, admin):
    api.include_router(module.router)


@api.get("/health", tags=["service"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(api)

settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
