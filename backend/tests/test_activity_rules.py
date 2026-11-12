"""Калибровка новичков, правило простоя и пересчёт истории миграцией 0007."""

import importlib.util
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal, engine, utcnow
from app.models import Fight, RatingChange, RatingDecay, User
from app.services.rating import CALIBRATION_FIGHTS, apply_inactivity, inactivity_penalty
from tests.conftest import (
    BACKEND_DIR,
    FIGHT_TIME,
    finish_tournament,
    new_tournament,
    play,
    run_tournament_start,
    set_points,
)


def rows_by_id(api) -> dict[int, dict]:
    return {row["player"]["id"]: row for row in api.get("/players").json()}


# Калибровка


def test_players_with_few_fights_go_below_calibrated(players):
    veteran, sparring, rookie, idle = players(4)
    for hour in range(CALIBRATION_FIGHTS):
        play(veteran, sparring, sparring if hour == 0 else veteran, FIGHT_TIME + timedelta(hours=hour))
    play(rookie, sparring, rookie, FIGHT_TIME + timedelta(days=1))
    set_points([rookie], 1500)

    rows = rows_by_id(veteran)
    assert rows[veteran.id]["is_calibrating"] is False
    assert rows[sparring.id]["is_calibrating"] is False
    assert rows[rookie.id]["is_calibrating"] is True
    assert rows[idle.id]["is_calibrating"] is True
    # У новичка больше всех очков, но он стоит после откалиброванных.
    order = [row["player"]["id"] for row in veteran.get("/players").json()]
    assert order == [veteran.id, sparring.id, rookie.id, idle.id]
    assert [rows[api.id]["display_place"] for api in (veteran, sparring, rookie, idle)] == [1, 2, 3, 4]

    profile = rookie.profile()["rating"]
    assert profile["is_calibrating"] is True
    assert profile["tier"] == "calibration"


def test_calibration_ends_after_fifth_fight(players):
    first, second = players(2)
    for hour in range(CALIBRATION_FIGHTS - 1):
        play(first, second, first, FIGHT_TIME + timedelta(hours=hour))
    assert rows_by_id(first)[first.id]["is_calibrating"] is True
    play(first, second, first, FIGHT_TIME + timedelta(hours=10))
    assert rows_by_id(first)[first.id]["is_calibrating"] is False


# Простой


def shift_fights(days: float) -> None:
    """Сдвигает подтверждение всех боёв в прошлое, как будто с тех пор прошло days дней."""
    with SessionLocal() as db:
        db.query(Fight).update({Fight.confirmed_at: Fight.confirmed_at - timedelta(days=days)})
        db.commit()


def run_inactivity(now=None) -> int:
    with SessionLocal() as db:
        return apply_inactivity(db, now)


def test_inactivity_penalty_values():
    assert inactivity_penalty(1000) == 0
    assert inactivity_penalty(950) == 0
    assert inactivity_penalty(1010) == 1
    assert inactivity_penalty(1100) == 3
    assert inactivity_penalty(1001) == 1


def test_no_penalty_during_first_two_weeks(players):
    winner, loser = players(2)
    play(winner, loser, winner)
    shift_fights(13)
    assert run_inactivity() == 0
    assert winner.points() == 1024


def test_weekly_penalty_after_two_weeks_only_above_start(players):
    winner, loser = players(2)
    play(winner, loser, winner)
    set_points([winner], 1100)
    shift_fights(14.1)
    assert run_inactivity() == 1
    assert winner.points() == 1097
    assert loser.points() == 982

    # Повторный запуск в ту же неделю ничего не меняет.
    assert run_inactivity() == 0
    assert winner.points() == 1097

    # Через три недели после срока снято ещё три раза, каждый от текущего превышения.
    assert run_inactivity(utcnow() + timedelta(days=21)) == 3
    assert winner.points() == 1097 - 3 - 3 - 3

    info = winner.profile()["rating"]["inactivity"]
    assert info["days_without_fights"] == 14
    assert info["lost_points"] == 12
    assert loser.profile()["rating"]["inactivity"] is None


def test_new_fight_stops_the_decay(players):
    winner, loser = players(2)
    play(winner, loser, winner)
    set_points([winner], 1100)
    shift_fights(15)
    assert run_inactivity() == 1
    play(winner, loser, winner)
    points = winner.points()
    assert run_inactivity(utcnow() + timedelta(days=13)) == 0
    assert winner.points() == points
    assert winner.profile()["rating"]["inactivity"] is None


def test_penalty_does_not_go_below_start(players):
    winner, loser = players(2)
    play(winner, loser, winner)
    set_points([winner], 1001)
    shift_fights(60)
    assert run_inactivity() == 1
    assert winner.points() == 1000
    with SessionLocal() as db:
        assert db.scalar(select(RatingDecay.delta)) == -1


# Пересчёт истории миграцией


def load_migration():
    path = BACKEND_DIR / "alembic" / "versions" / "0007_activity_rating.py"
    spec = importlib.util.spec_from_file_location("migration_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot() -> tuple[dict, list]:
    with SessionLocal() as db:
        points = dict(db.execute(select(User.id, User.rating_points)).all())
        changes = db.execute(
            select(
                RatingChange.fight_id,
                RatingChange.player_id,
                RatingChange.place_before,
                RatingChange.points_before,
                RatingChange.delta,
                RatingChange.loss_discount,
                RatingChange.points_after,
                RatingChange.place_after,
            ).order_by(RatingChange.fight_id, RatingChange.player_id)
        ).all()
    return points, [tuple(row) for row in changes]


def test_migration_replay_matches_live_rules(admin, players):
    """Пересчёт миграции даёт ровно то же, что начисления при подтверждении боёв."""
    apis = players(6)
    first, second, third, *_ = apis
    for hour in range(12):
        winner = first if hour % 3 else second
        play(first, second, winner, FIGHT_TIME + timedelta(hours=hour))
    play(third, first, third)
    play(second, third, second)
    tournament = new_tournament(admin, capacity=4, win_points=30)
    run_tournament_start(admin, tournament["id"], apis[2:])
    finish_tournament(admin, apis[2:], tournament["id"], champion=apis[3])
    play(apis[5], first, apis[5])

    before = snapshot()
    with SessionLocal() as db:
        db.query(User).update({User.rating_points: 1000})
        db.query(RatingChange).delete()
        db.commit()
    with engine.begin() as connection:
        load_migration().recalculate(connection)
    assert snapshot() == before
