from concurrent.futures import ThreadPoolExecutor

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

    autos = {item["player"]["id"]: item["delta"] for item in created.json()["rating_changes"]}
    assert autos == {bottom.id: 5, top.id: -5}

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

    pending = create_fight(apis[1], apis[2], apis[1]).json()
    assert admin.put(f"/admin/rating/adjustments/{pending['id']}", body(apis[1], 2)).status_code == 409

    regular = play(apis[1], apis[2], apis[1])
    assert admin.put(f"/admin/rating/adjustments/{regular['id']}", body(apis[1], 2)).status_code == 409
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

    table = top.get("/players").json()
    assert table[0]["player"]["id"] == fourth.id
    assert table[0]["display_place"] == 1
    assert table[0]["is_special"] is True
    assert table[0]["points_place"] == 4
    assert fourth.profile()["rating"]["is_special"] is True

    top_before, fourth_before = top.points(), fourth.points()
    play(fourth, top, fourth)
    assert fourth.points() == fourth_before + 5
    assert top.points() == top_before - 5

    other = apis[1]
    taken = admin.put(f"/admin/rating/special-places/{other.id}", {"place": 1})
    assert taken.status_code == 409
    assert fourth.user["nickname"] in taken.json()["detail"]

    assert admin.delete(f"/admin/rating/special-places/{fourth.id}").status_code == 204
    table = top.get("/players").json()
    row = next(item for item in table if item["player"]["id"] == fourth.id)
    assert row["is_special"] is False
    assert row["display_place"] == row["points_place"]


def test_remaining_groups_fill_free_numbers(admin, players):
    first, second, third, fourth, fifth = players(5)
    play(first, second, first)
    # Очки: first 102, third/fourth/fifth 100, second 98. Спецместо №2 у игрока second.
    assert admin.put(f"/admin/rating/special-places/{second.id}", {"place": 2}).status_code == 200
    rows = {row["player"]["id"]: row for row in first.get("/players").json()}
    assert rows[first.id]["display_place"] == 1
    assert rows[second.id]["display_place"] == 2
    assert rows[third.id]["display_place"] == 3
    assert rows[fourth.id]["display_place"] == 3
    assert rows[fifth.id]["display_place"] == 3


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
    rows = first.get("/players").json()
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
    assert first.points() == 100
