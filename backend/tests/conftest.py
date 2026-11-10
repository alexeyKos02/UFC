import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://ufc:ufc@localhost:5432/ufc_test")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="ufc-test-uploads-")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, UserRole  # noqa: E402
from app.services import accounts  # noqa: E402

# Быстрый хеш только для тестов: сотни регистраций иначе занимают минуты.
security.hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

PASSWORD = "password123"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _ensure_database()
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        connection.execute(text("INSERT INTO belts (kind, name) VALUES ('main', 'Чемпион лиги')"))
    yield


class Api:
    """Клиент одного пользователя со своей cookie-сессией."""

    def __init__(self, login: str, user: dict | None = None):
        self.client = TestClient(app, raise_server_exceptions=True)
        self.login = login
        self.user = user or {}

    @property
    def id(self) -> int:
        return self.user["id"]

    def get(self, url: str, **kwargs):
        return self.client.get(f"/api{url}", **kwargs)

    def post(self, url: str, json=None, **kwargs):
        return self.client.post(f"/api{url}", json=json, **kwargs)

    def put(self, url: str, json=None, **kwargs):
        return self.client.put(f"/api{url}", json=json, **kwargs)

    def patch(self, url: str, json=None, **kwargs):
        return self.client.patch(f"/api{url}", json=json, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.client.delete(f"/api{url}", **kwargs)

    def points(self) -> int:
        return self.get("/auth/me").json()["rating_points"]

    def profile(self) -> dict:
        return self.get(f"/players/{self.id}").json()


def register(login: str) -> Api:
    api = Api(login)
    response = api.post("/auth/register", {"login": login, "password": PASSWORD})
    assert response.status_code == 201, response.text
    api.user = response.json()
    return api


def privileged(login: str, role: UserRole) -> Api:
    db = SessionLocal()
    try:
        accounts.create_user(db, login, PASSWORD, role=role)
        db.commit()
    finally:
        db.close()
    api = Api(login)
    response = api.post("/auth/login", {"login": login, "password": PASSWORD})
    assert response.status_code == 200, response.text
    api.user = response.json()
    return api


@pytest.fixture
def owner() -> Api:
    return privileged("owner", UserRole.OWNER)


@pytest.fixture
def admin() -> Api:
    return privileged("admin", UserRole.ADMIN)


@pytest.fixture
def players():
    def make(count: int, prefix: str = "player") -> list[Api]:
        return [register(f"{prefix}{index}") for index in range(1, count + 1)]

    return make


FIGHT_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def iso(moment: datetime | None = None) -> str:
    return (moment or FIGHT_TIME).isoformat()


def result_body(winner_id: int, moment: datetime | None = None, **extra) -> dict:
    return {"fought_at": iso(moment), "winner_id": winner_id, **extra}


def create_fight(initiator: Api, opponent: Api, winner: Api, moment: datetime | None = None, **extra):
    body = {
        **result_body(winner.id, moment),
        "opponent_id": opponent.id,
        "client_request_id": str(uuid.uuid4()),
        **extra,
    }
    return initiator.post("/fights", body)


def confirm(api: Api, fight: dict):
    return api.post(f"/fights/{fight['id']}/confirm", {"version_no": fight["version_no"]})


def play(initiator: Api, opponent: Api, winner: Api, moment: datetime | None = None) -> dict:
    created = create_fight(initiator, opponent, winner, moment)
    assert created.status_code == 201, created.text
    confirmed = confirm(opponent, created.json())
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    return confirmed.json()


def ladder(apis: list[Api]) -> None:
    """Выстраивает строго убывающие очки: apis[0] выше всех, каждая пара соседей — разные места."""
    base = FIGHT_TIME - timedelta(days=400)
    step = 0
    for upper_index, upper in enumerate(apis):
        for lower in apis[upper_index + 1:]:
            step += 1
            play(upper, lower, upper, base + timedelta(hours=step))


def belt_body(name: str) -> dict:
    return {"name": name}


def new_belt(staff: Api, name: str = "Пояс новичков") -> dict:
    response = staff.post("/admin/belts", belt_body(name))
    assert response.status_code == 201, response.text
    return response.json()


def new_tournament(staff: Api, capacity: int = 8, belt: dict | None = None, publish: bool = True) -> dict:
    belt = belt or new_belt(staff, f"Пояс {uuid.uuid4().hex[:6]}")
    response = staff.post(
        "/admin/tournaments",
        {"title": "Кубок лиги", "description": "Тест", "capacity": capacity, "belt_id": belt["id"]},
    )
    assert response.status_code == 201, response.text
    tournament = response.json()
    if publish:
        published = staff.post(f"/admin/tournaments/{tournament['id']}/publish")
        assert published.status_code == 200, published.text
        tournament = published.json()
    return tournament


def run_tournament_start(staff: Api, tournament_id: int, participants: list[Api]) -> dict:
    for participant in participants:
        joined = participant.post(f"/tournaments/{tournament_id}/join")
        assert joined.status_code == 200, joined.text
    started = staff.post(f"/admin/tournaments/{tournament_id}/start")
    assert started.status_code == 200, started.text
    return started.json()


def tournament_state(api: Api, tournament_id: int) -> dict:
    return api.get(f"/tournaments/{tournament_id}").json()


def playable_matches(state: dict) -> list[dict]:
    return [match for rnd in state["rounds"] for match in rnd["matches"] if match["state"] == "ready"]


def play_match(by_id: dict[int, Api], match: dict, winner_id: int | None = None) -> dict:
    first = by_id[match["player1"]["id"]]
    second = by_id[match["player2"]["id"]]
    winner_id = winner_id or first.id
    submitted = first.post(f"/tournaments/matches/{match['id']}/result", result_body(winner_id))
    assert submitted.status_code == 201, submitted.text
    confirmed = confirm(second, submitted.json())
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def finish_tournament(staff: Api, participants: list[Api], tournament_id: int, champion: Api | None = None) -> dict:
    by_id = {participant.id: participant for participant in participants}
    while True:
        state = tournament_state(staff, tournament_id)
        ready = playable_matches(state)
        if not ready:
            assert state["status"] == "finished", state
            return state
        match = ready[0]
        pair = [match["player1"]["id"], match["player2"]["id"]]
        winner_id = champion.id if champion and champion.id in pair else pair[0]
        play_match(by_id, match, winner_id)
