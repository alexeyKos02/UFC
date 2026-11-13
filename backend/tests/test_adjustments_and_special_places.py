from concurrent.futures import ThreadPoolExecutor

from tests.conftest import expected_gain
from tests.conftest import confirm, create_fight, ladder, play


def upset_setup(players):
    apis = players(4)
    ladder(apis)
    top, _, _, bottom = apis
    fight = play(bottom, top, bottom)
    return top, bottom, fight, apis


def body(player, points, version=0, reason="Исключительный апсет"):
    return {"player_id": player.id, "points": points, "reason": reason, "expected_version": version}


def test_adjustment_add_change_and_cancel(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    top_start, bottom_start = top.points(), bottom.points()

    created = admin.put(url, body(bottom, 2))
    assert created.status_code == 200
    assert created.json()["adjustment"]["winner_delta"] == 2
    assert created.json()["adjustment"]["loser_delta"] == -2
    assert bottom.points() == bottom_start + 2
    assert top.points() == top_start - 2

    autos = {item["player"]["id"]: item for item in created.json()["rating_changes"]}
    upset_gain = expected_gain(autos[bottom.id]["points_before"], autos[top.id]["points_before"])
    assert upset_gain > 20
    assert autos[bottom.id]["delta"] == upset_gain
    # Проигравший получил скидку за активность и потерял меньше.
    assert -upset_gain < autos[top.id]["delta"] < 0

    changed = admin.put(url, body(bottom, 3, version=1, reason="Пересмотр"))
    assert changed.json()["adjustment"]["winner_delta"] == 3
    assert bottom.points() == bottom_start + 3
    assert top.points() == top_start - 3

    cancelled = admin.post(f"{url}/cancel", {"reason": "Отмена решения", "expected_version": 2})
    assert cancelled.status_code == 200
    assert cancelled.json()["adjustment"] is None
    assert bottom.points() == bottom_start
    assert top.points() == top_start

    log = admin.get("/admin/rating/adjustment-log").json()
    assert [row["action"] for row in log] == ["cancel", "update", "create"]
    assert log[0]["actor"]["id"] == admin.id
    assert log[0]["reason"] == "Отмена решения"
    assert log[0]["winner_delta_before"] == 3
    assert log[0]["winner_delta_after"] == 0
    assert log[2]["winner_points_before"] == bottom_start
    assert log[2]["winner_points_after"] == bottom_start + 2
    assert log[2]["loser_points_after"] == top_start - 2


def test_adjustment_by_owner_and_for_loser(owner, players):
    top, bottom, fight, _ = upset_setup(players)
    top_start, bottom_start = top.points(), bottom.points()
    response = owner.put(f"/admin/rating/adjustments/{fight['id']}", body(top, 4))
    assert response.status_code == 200
    assert response.json()["adjustment"]["winner_delta"] == -4
    assert top.points() == top_start + 4
    assert bottom.points() == bottom_start - 4


def test_replay_does_not_change_points_twice(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    bottom_start = bottom.points()
    first = admin.put(url, body(bottom, 2))
    second = admin.put(url, body(bottom, 2))
    assert first.status_code == second.status_code == 200
    assert bottom.points() == bottom_start + 2
    assert len(admin.get("/admin/rating/adjustment-log").json()) == 1


def test_parallel_saves_apply_once(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    bottom_start = bottom.points()
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: admin.put(url, body(bottom, 2)), range(8)))
    assert {response.status_code for response in responses} == {200}
    assert bottom.points() == bottom_start + 2


def test_stale_version_rejected(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    bottom_start = bottom.points()
    admin.put(url, body(bottom, 2))
    admin.put(url, body(bottom, 3, version=1))
    assert admin.put(url, body(bottom, 7, version=1)).status_code == 409
    assert bottom.points() == bottom_start + 3


def test_repeat_cancel_returns_points_once(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    bottom_start = bottom.points()
    admin.put(url, body(bottom, 2))
    assert admin.post(f"{url}/cancel", {"reason": "Отмена", "expected_version": 1}).status_code == 200
    assert admin.post(f"{url}/cancel", {"reason": "Отмена", "expected_version": 1}).status_code == 200
    assert bottom.points() == bottom_start
    assert len(admin.get("/admin/rating/adjustment-log").json()) == 2


def test_adjustment_can_be_recreated_after_cancel(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    bottom_start = bottom.points()
    admin.put(url, body(bottom, 2))
    admin.post(f"{url}/cancel", {"reason": "Отмена", "expected_version": 1})
    again = admin.put(url, body(bottom, 1, version=2))
    assert again.status_code == 200
    assert bottom.points() == bottom_start + 1


def test_rejects_player_unconfirmed_and_non_upset(admin, players):
    top, bottom, fight, apis = upset_setup(players)
    url = f"/admin/rating/adjustments/{fight['id']}"
    assert bottom.put(url, body(bottom, 2)).status_code == 403

    regular = play(apis[1], apis[2], apis[1])
    assert admin.put(f"/admin/rating/adjustments/{regular['id']}", body(apis[1], 2)).status_code == 409

    pending = create_fight(apis[1], apis[2], apis[1]).json()
    assert admin.put(f"/admin/rating/adjustments/{pending['id']}", body(apis[1], 2)).status_code == 409
    assert admin.put(url, body(apis[1], 2)).status_code == 400
    assert admin.put(url, body(bottom, 0)).status_code == 400


def test_adjustment_requires_reason(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    payload = body(bottom, 2, reason="")
    assert admin.put(f"/admin/rating/adjustments/{fight['id']}", payload).status_code == 422


def test_adjustment_does_not_touch_other_fights(admin, players):
    top, bottom, fight, apis = upset_setup(players)
    middle_points = apis[1].points()
    admin.put(f"/admin/rating/adjustments/{fight['id']}", body(bottom, 2))
    assert apis[1].points() == middle_points


def test_upset_list_contains_only_upsets(admin, players):
    top, bottom, fight, apis = upset_setup(players)
    play(apis[1], apis[2], apis[1])
    upsets = admin.get("/admin/rating/upsets").json()
    assert [row["fight_id"] for row in upsets] == [fight["id"]]
    assert upsets[0]["winner_place_before"] - upsets[0]["loser_place_before"] >= 3


def test_special_place_scenario_from_spec(admin, players):
    # Админ тоже активный игрок, поэтому он входит в лестницу из четырёх мест.
    top, second, fourth = players(3)
    apis = [top, second, admin, fourth]
    ladder(apis)
    assert admin.put(f"/admin/rating/special-places/{fourth.id}", {"place": 1}).status_code == 200

    table = admin.get("/players").json()
    assert table[0]["player"]["id"] == fourth.id
    assert table[0]["display_place"] == 1
    assert table[0]["is_special"] is True
    assert table[0]["points_place"] == 4
    assert admin.get(f"/players/{fourth.id}").json()["rating"]["is_special"] is True

    top_before, fourth_before = top.points(), fourth.points()
    play(fourth, top, fourth)
    gain = expected_gain(fourth_before, top_before)
    assert gain > 20
    assert fourth.points() == fourth_before + gain
    assert top_before - gain < top.points() < top_before

    other = apis[1]
    taken = admin.put(f"/admin/rating/special-places/{other.id}", {"place": 1})
    assert taken.status_code == 409
    assert fourth.user["nickname"] in taken.json()["detail"]

    assert admin.delete(f"/admin/rating/special-places/{fourth.id}").status_code == 204
    table = admin.get("/players").json()
    row = next(item for item in table if item["player"]["id"] == fourth.id)
    assert row["is_special"] is False
    assert row["display_place"] == row["points_place"]


def test_special_place_marker_is_visible_only_to_staff(owner, admin, players):
    pinned, other = players(2)
    assert admin.put(f"/admin/rating/special-places/{pinned.id}", {"place": 1}).status_code == 200

    def views(api):
        row = next(item for item in api.get("/players").json() if item["player"]["id"] == pinned.id)
        return row, api.get(f"/players/{pinned.id}").json()["rating"]

    for player in (pinned, other):
        row, rating = views(player)
        assert row["display_place"] == 1
        assert row["is_special"] is False
        assert row["points_place"] is None
        assert rating["display_place"] == 1
        assert rating["is_special"] is False
        assert rating["points_place"] is None

    for staff in (admin, owner):
        row, rating = views(staff)
        assert row["is_special"] is True
        assert row["points_place"] == 1
        assert rating["is_special"] is True
        assert rating["points_place"] == 1


def test_remaining_players_fill_free_numbers(admin, players):
    first, second, third, fourth, fifth = players(5)
    play(first, second, first)
    # Очки: first 1024, admin/third/fourth/fifth 1000, second 982. Спецместо №2 у игрока second.
    assert admin.put(f"/admin/rating/special-places/{second.id}", {"place": 2}).status_code == 200
    rows = {row["player"]["id"]: row for row in first.get("/players").json()}
    order = (first, second, admin, third, fourth, fifth)
    assert [rows[api.id]["display_place"] for api in order] == [1, 2, 3, 4, 5, 6]


def test_special_place_change_and_log(admin, players):
    first, second, third = players(3)
    url = f"/admin/rating/special-places/{first.id}"
    admin.put(url, {"place": 3})
    admin.put(url, {"place": 2})
    admin.delete(url)
    log = admin.get("/admin/rating/special-place-log").json()
    assert [(row["action"], row["place_before"], row["place_after"]) for row in log] == [
        ("clear", 2, None),
        ("change", 3, 2),
        ("set", None, 3),
    ]
    assert log[0]["actor"]["id"] == admin.id


def test_special_place_range_checks(admin, players):
    first, second = players(2)
    url = f"/admin/rating/special-places/{first.id}"
    assert admin.put(url, {"place": 0}).status_code == 400
    # Активны: admin и два игрока.
    assert admin.put(url, {"place": 4}).status_code == 400
    assert admin.put(url, {"place": 3}).status_code == 200


def test_special_place_requires_active_player(owner, admin, players):
    first = players(1)[0]
    owner.post(f"/admin/users/{first.id}/block")
    assert admin.put(f"/admin/rating/special-places/{first.id}", {"place": 1}).status_code == 409


def test_one_number_per_player(admin, players):
    first, second, third = players(3)
    url = f"/admin/rating/special-places/{first.id}"
    admin.put(url, {"place": 1})
    admin.put(url, {"place": 2})
    data = admin.get("/admin/rating").json()
    assert [(item["player"]["id"], item["place"]) for item in data["special_places"]] == [(first.id, 2)]


def test_blocked_holder_hidden_and_restored(owner, admin, players):
    first, second, third = players(3)
    admin.put(f"/admin/rating/special-places/{third.id}", {"place": 1})
    owner.post(f"/admin/users/{third.id}/block")

    rows = first.get("/players").json()
    assert third.id not in [row["player"]["id"] for row in rows]
    assert min(row["display_place"] for row in rows) == 1
    number_still_held = admin.put(f"/admin/rating/special-places/{first.id}", {"place": 1})
    assert number_still_held.status_code == 409
    assert third.user["nickname"] in number_still_held.json()["detail"]

    owner.post(f"/admin/users/{third.id}/unblock")
    rows = admin.get("/players").json()
    assert rows[0]["player"]["id"] == third.id
    assert rows[0]["is_special"] is True


def test_database_enforces_unique_special_number(admin, players):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models import SpecialPlace

    first, second = players(2)
    admin.put(f"/admin/rating/special-places/{first.id}", {"place": 1})
    db = SessionLocal()
    db.add(SpecialPlace(user_id=second.id, place=1, updated_by_id=admin.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_parallel_claims_for_same_number_admit_one(admin, players):
    apis = players(6)
    with ThreadPoolExecutor(len(apis)) as pool:
        responses = list(
            pool.map(lambda api: admin.put(f"/admin/rating/special-places/{api.id}", {"place": 1}), apis)
        )
    codes = [response.status_code for response in responses]
    assert codes.count(200) == 1
    assert codes.count(409) == len(apis) - 1


def test_rejected_fight_confirm_leaves_rating(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    second.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Спор"})
    assert confirm(second, fight).status_code == 409
    assert first.points() == 1000
