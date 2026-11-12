"""Номер в таблице рейтинга до и после боя: с чемпионом, калибровкой и спецместами."""

import importlib.util
from datetime import timedelta

from sqlalchemy import select, update

from app.db import SessionLocal, engine
from app.models import RatingChange
from tests.conftest import (
    BACKEND_DIR,
    FIGHT_TIME,
    finish_tournament,
    new_tournament,
    play,
    run_tournament_start,
)
from tests.test_belts import play_title, schedule


def change_of(fight: dict, player) -> dict:
    return next(item for item in fight["rating_changes"] if item["player"]["id"] == player.id)


def table_number(viewer, player) -> int | None:
    return next(row["display_place"] for row in viewer.get("/players").json() if row["player"]["id"] == player.id)


def test_new_fight_stores_table_number_and_keeps_points_place(players):
    first, second, third = players(3)
    play(first, second, first)
    fight = play(third, first, third)
    winner, loser = change_of(fight, third), change_of(fight, first)
    # Все в калибровке: номер в таблице идёт по очкам, место по очкам тоже хранится.
    assert (winner["table_place_before"], winner["table_place_after"]) == (2, 1)
    assert (loser["table_place_before"], loser["table_place_after"]) == (1, 2)
    assert winner["place_before"] == 2 and winner["place_after"] == 1
    assert winner["champion_before"] is False and winner["champion_after"] is False
    assert table_number(first, third) == winner["table_place_after"]


def test_champion_has_no_number_and_others_shift(admin, players):
    champion, challenger, other = players(3)
    title = schedule(admin, challenger, champion).json()
    play_title(title, champion, challenger, champion)

    fight = play(other, challenger, other)
    winner, loser = change_of(fight, other), change_of(fight, challenger)
    # Чемпион по очкам первый, но стоит над таблицей: остальные нумеруются с №1.
    assert winner["place_after"] == 2 and winner["table_place_after"] == 1
    assert loser["table_place_after"] == table_number(other, challenger)


def test_title_fight_after_shows_new_champion(admin, players):
    champion, challenger = players(2)
    title = schedule(admin, challenger, champion).json()
    fight = play_title(title, champion, challenger, challenger)
    winner = change_of(fight, challenger)
    assert winner["champion_before"] is False
    assert winner["table_place_after"] is None and winner["champion_after"] is True
    loser = change_of(fight, champion)
    # Админ тоже в таблице с 1000 очков, поэтому проигравший — №2.
    assert loser["champion_before"] is False and loser["table_place_after"] == 2
    assert loser["table_place_after"] == table_number(admin, champion)


def test_calibrating_player_is_numbered_below_calibrated(players):
    veteran, sparring, rookie = players(3)
    for hour in range(5):
        play(veteran, sparring, sparring if hour == 0 else veteran, FIGHT_TIME + timedelta(hours=hour))
    fight = play(rookie, sparring, rookie, FIGHT_TIME + timedelta(days=1))
    change = change_of(fight, rookie)
    # По очкам новичок выше проигравшего, но в таблице после двух откалиброванных.
    assert change["table_place_after"] == 3
    assert change["place_after"] < 3


def test_special_place_is_used_as_table_number(admin, players):
    first, second = players(2)
    assert admin.put(f"/admin/rating/special-places/{second.id}", {"place": 1}).status_code == 200
    fight = play(first, second, first)
    assert change_of(fight, second)["table_place_after"] == 1
    assert change_of(fight, first)["table_place_after"] == 2


# Пересчёт истории миграцией 0008


def load_migration():
    path = BACKEND_DIR / "alembic" / "versions" / "0008_table_places.py"
    spec = importlib.util.spec_from_file_location("migration_0008", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stored() -> list[tuple]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                RatingChange.fight_id,
                RatingChange.player_id,
                RatingChange.table_place_before,
                RatingChange.table_place_after,
                RatingChange.champion_before,
                RatingChange.champion_after,
            ).order_by(RatingChange.fight_id, RatingChange.player_id)
        ).all()
    return [tuple(row) for row in rows]


def test_migration_backfill_matches_live_numbers(owner, admin, players):
    apis = players(7)
    a, b, c, d, e, f, g = apis
    for hour in range(6):
        play(a, b, a if hour % 3 else b, FIGHT_TIME + timedelta(hours=hour))
    play(c, d, c)
    play(c, a, a)
    assert admin.put(f"/admin/rating/special-places/{d.id}", {"place": 2}).status_code == 200
    play(e, d, e)
    title = schedule(admin, c, a).json()
    play_title(title, a, c, c)
    play(a, b, b)
    play(b, f, f)
    assert admin.delete(f"/admin/rating/special-places/{d.id}").status_code == 204
    play(d, e, d)
    tournament = new_tournament(admin, capacity=4, win_points=30)
    run_tournament_start(admin, tournament["id"], [d, e, f, g])
    finish_tournament(admin, [d, e, f, g], tournament["id"], champion=g)
    belt_main = admin.get("/belts").json()[0]
    assert admin.post(f"/admin/belts/{belt_main['id']}/award", {"player_id": e.id}).status_code == 200
    play(g, a, g)

    live = stored()
    assert all(row[2] is not None or row[4] for row in live)
    with SessionLocal() as db:
        db.execute(
            update(RatingChange).values(
                table_place_before=None, table_place_after=None, champion_before=False, champion_after=False
            )
        )
        db.commit()
    with engine.begin() as connection:
        load_migration().backfill(connection)
    assert stored() == live


def test_rating_history_lists_points_and_places_in_order(admin, players):
    first, second, third = players(3)
    play(first, second, first, FIGHT_TIME)
    play(third, first, third, FIGHT_TIME + timedelta(hours=1))
    title = schedule(admin, third, first).json()
    play_title(title, first, third, first)

    history = second.get(f"/players/{first.id}/rating-history").json()["points"]
    assert [item["won"] for item in history] == [True, False, True]
    assert [item["opponent"]["id"] for item in history] == [second.id, third.id, third.id]
    assert history[0]["points_before"] == 1000
    for previous, current in zip(history, history[1:], strict=False):
        assert current["points_before"] == previous["points_after"]
    assert history[-1]["points_after"] == first.points()
    assert history[-1]["champion_after"] is True and history[-1]["table_place_after"] is None
    assert history[-1]["kind"] == "title"

    assert second.get(f"/players/{admin.id}/rating-history").json()["points"] == []
    assert second.get("/players/999999/rating-history").status_code == 404
