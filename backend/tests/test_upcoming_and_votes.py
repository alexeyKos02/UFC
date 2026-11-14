import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from tests.conftest import (
    confirm,
    create_fight,
    new_tournament,
    play,
    result_body,
    run_tournament_start,
)
from tests.test_belts import schedule


def future(days: int = 3) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


def plan(initiator, opponent, when: datetime | None = None, key: str | None = None):
    return initiator.post(
        "/fights/planned",
        {
            "opponent_id": opponent.id,
            "scheduled_at": (when or future()).isoformat(),
            "client_request_id": key or str(uuid.uuid4()),
        },
    )


def upcoming(api) -> list[dict]:
    return api.get("/fights/upcoming").json()


def vote(api, item: dict, player):
    return api.put(f"/fights/upcoming/{item['kind']}/{item['id']}/vote", {"player_id": player.id})


def votes_of(api, item: dict) -> dict:
    return next(row["votes"] for row in upcoming(api) if (row["kind"], row["id"]) == (item["kind"], item["id"]))


def brief_of(api, fight_id: int) -> dict:
    return next(row for row in api.get("/fights").json()["items"] if row["id"] == fight_id)


def test_place_after_is_stored_for_both_players(players):
    first, second, third = players(3)
    fight = play(first, second, first)
    changes = {item["player"]["id"]: item for item in fight["rating_changes"]}
    assert (changes[first.id]["place_before"], changes[first.id]["place_after"]) == (1, 1)
    # После боя: first 1024, third 1000, second 982.
    assert (changes[second.id]["place_before"], changes[second.id]["place_after"]) == (1, 3)


def test_planned_fight_is_listed_and_changes_nothing(players):
    first, second, witness = players(3)
    created = plan(first, second)
    assert created.status_code == 201
    item = created.json()
    assert item["kind"] == "planned"

    assert [row["id"] for row in upcoming(witness)] == [item["id"]]
    assert witness.get("/fights").json()["total"] == 0
    assert first.points() == 1000
    assert first.profile()["stats"]["all"]["fights"] == 0
    assert [row["id"] for row in second.get("/fights/mine").json()["upcoming"]] == [item["id"]]
    assert witness.get("/fights/mine").json()["upcoming"] == []


def test_planned_fight_validation(owner, players):
    first, second = players(2)
    assert plan(first, second, datetime.now(UTC) - timedelta(minutes=1)).status_code == 400
    assert plan(first, first).status_code == 400
    owner.post(f"/admin/users/{second.id}/block")
    assert plan(first, second).status_code == 409


def test_replayed_planning_returns_same_record(players):
    first, second = players(2)
    key = str(uuid.uuid4())
    one = plan(first, second, key=key)
    two = plan(first, second, key=key)
    assert one.json()["id"] == two.json()["id"]
    assert len(upcoming(first)) == 1


def test_parallel_planning_with_same_key_makes_one_record(players):
    first, second = players(2)
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: plan(first, second, key=key), range(8)))
    assert {response.status_code for response in responses} == {201}
    assert len(upcoming(first)) == 1


def test_result_of_planned_fight_goes_through_confirmation(players):
    first, second = players(2)
    item = plan(first, second).json()

    submitted = second.post(f"/fights/planned/{item['id']}/result", result_body(second.id))
    assert submitted.status_code == 201
    fight = submitted.json()
    assert fight["status"] == "pending"
    assert fight["kind"] == "regular"
    assert upcoming(first) == []
    assert first.points() == 1000

    assert confirm(first, fight).json()["status"] == "confirmed"
    assert second.points() == 1024
    assert first.points() == 982


def test_planned_result_rules(players):
    first, second, outsider = players(3)
    item = plan(first, second).json()
    url = f"/fights/planned/{item['id']}/result"
    assert outsider.post(url, result_body(first.id)).status_code == 403
    assert first.post(url, result_body(outsider.id)).status_code == 400
    one = first.post(url, result_body(first.id))
    assert one.status_code == 201
    assert first.post(url, result_body(first.id)).json()["id"] == one.json()["id"]
    assert second.post(url, result_body(second.id)).status_code == 409


def test_planned_fight_cancel_rules(admin, players):
    first, second, outsider = players(3)
    item = plan(first, second).json()
    assert outsider.post(f"/fights/planned/{item['id']}/cancel").status_code == 403
    assert second.post(f"/fights/planned/{item['id']}/cancel").status_code == 204
    assert upcoming(first) == []
    assert first.post(f"/fights/planned/{item['id']}/result", result_body(first.id)).status_code == 409

    by_staff = plan(first, second).json()
    assert admin.post(f"/fights/planned/{by_staff['id']}/cancel").status_code == 204

    played = plan(first, second).json()
    first.post(f"/fights/planned/{played['id']}/result", result_body(first.id))
    assert first.post(f"/fights/planned/{played['id']}/cancel").status_code == 409


def test_viewers_vote_and_can_change_their_vote(admin, players):
    first, second, viewer = players(3)
    item = plan(first, second).json()

    assert vote(viewer, item, first).status_code == 204
    assert vote(admin, item, second).status_code == 204
    assert votes_of(viewer, item) == {"first": 1, "second": 1, "my_vote": first.id}

    assert vote(viewer, item, second).status_code == 204
    assert votes_of(viewer, item) == {"first": 0, "second": 2, "my_vote": second.id}
    assert votes_of(first, item)["my_vote"] is None


def test_participants_cannot_vote_and_choice_must_be_in_pair(players):
    first, second, viewer, other = players(4)
    item = plan(first, second).json()
    assert vote(first, item, first).status_code == 403
    assert vote(second, item, first).status_code == 403
    assert vote(viewer, item, other).status_code == 400
    assert votes_of(viewer, item) == {"first": 0, "second": 0, "my_vote": None}
    listed = next(row for row in upcoming(first))
    assert listed["can_vote"] is False
    assert next(row for row in upcoming(viewer))["can_vote"] is True


def test_parallel_votes_of_one_viewer_count_once(players):
    first, second, viewer = players(3)
    item = plan(first, second).json()
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: vote(viewer, item, first), range(8)))
    assert {response.status_code for response in responses} == {204}
    assert votes_of(viewer, item)["first"] == 1


def test_voting_closes_with_result_and_cancel(players):
    first, second, viewer = players(3)
    item = plan(first, second).json()
    first.post(f"/fights/planned/{item['id']}/result", result_body(first.id))
    assert vote(viewer, item, first).status_code == 409

    cancelled = plan(first, second).json()
    first.post(f"/fights/planned/{cancelled['id']}/cancel")
    assert vote(viewer, cancelled, first).status_code == 409


def test_votes_are_shown_after_the_fight(players):
    first, second, viewer, other = players(4)
    item = plan(first, second).json()
    vote(viewer, item, first)
    vote(other, item, second)
    fight = first.post(f"/fights/planned/{item['id']}/result", result_body(first.id)).json()
    assert second.get("/fights/mine").json()["to_confirm"][0]["votes"]["first"] == 1
    confirm(second, fight)

    assert brief_of(viewer, fight["id"])["votes"] == {"first": 1, "second": 1, "my_vote": first.id}
    assert viewer.get(f"/fights/{fight['id']}").json()["votes"]["second"] == 1


def test_fight_recorded_after_the_game_has_no_voting(players):
    first, second = players(2)
    fight = play(first, second, first)
    assert brief_of(first, fight["id"])["votes"] is None
    assert create_fight(first, second, first).json()["votes"] is None


def test_title_fight_is_open_for_votes(admin, players):
    first, second, viewer = players(3)
    title_fight = schedule(admin, second, first).json()
    item = next(row for row in upcoming(viewer) if row["kind"] == "title")
    assert item["id"] == title_fight["id"]
    assert vote(viewer, item, second).status_code == 204

    submitted = first.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).json()
    assert [row for row in upcoming(viewer) if row["kind"] == "title"] == []
    assert vote(viewer, item, first).status_code == 409
    confirmed = confirm(second, submitted).json()
    assert confirmed["votes"]["second"] == 1


def test_only_ready_tournament_matches_are_open_for_votes(admin, players):
    apis = players(3)
    viewer = players(1, prefix="viewer")[0]
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    ready = next(match for match in state["rounds"][0]["matches"] if match["state"] == "ready")
    bye = next(match for match in state["rounds"][0]["matches"] if match["is_bye"])
    final = state["rounds"][1]["matches"][0]

    items = [row for row in upcoming(viewer) if row["kind"] == "tournament"]
    assert [row["id"] for row in items] == [ready["id"]]
    assert items[0]["tournament"]["id"] == tournament["id"]
    assert items[0]["round_name"] == "Полуфинал"

    player_in_bye = next(api for api in apis if api.id == bye["player1"]["id"])
    bye_item = {"kind": "tournament", "id": bye["id"]}
    final_item = {"kind": "tournament", "id": final["id"]}
    assert vote(viewer, bye_item, player_in_bye).status_code == 409
    assert vote(viewer, final_item, player_in_bye).status_code == 409

    fighter = next(api for api in apis if api.id == ready["player1"]["id"])
    assert vote(viewer, items[0], fighter).status_code == 204
    assert votes_of(viewer, items[0])["first"] == 1


def test_vote_for_unknown_fight_and_kind(players):
    first, second, viewer = players(3)
    assert viewer.put("/fights/upcoming/planned/999/vote", {"player_id": first.id}).status_code == 404
    assert viewer.put("/fights/upcoming/bad/1/vote", {"player_id": first.id}).status_code == 422


def test_new_title_fight_is_on_home_page_with_votes(admin, players):
    first, second, witness = players(3)
    created = schedule(admin, second, first)
    assert created.status_code == 201, created.text
    bouts = witness.get("/home").json()["title_fights"]
    assert [bout["id"] for bout in bouts] == [created.json()["id"]]
    assert bouts[0]["kind"] == "title"
    assert bouts[0]["can_vote"] is True

    vote = witness.put(f"/fights/upcoming/title/{bouts[0]['id']}/vote", {"player_id": first.id})
    assert vote.status_code == 204
    assert witness.get("/home").json()["title_fights"][0]["votes"]["my_vote"] == first.id

    # После внесения результата бой уходит с главной.
    first.post(f"/title-fights/{bouts[0]['id']}/result", result_body(first.id))
    assert witness.get("/home").json()["title_fights"] == []
