import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from tests.conftest import FIGHT_TIME, confirm, create_fight, iso, play, result_body


def test_fight_counts_only_after_second_confirmation(players):
    first, second = players(2)
    created = create_fight(first, second, first, method="ko_tko", round=2)
    assert created.status_code == 201
    fight = created.json()
    assert fight["status"] == "pending"
    assert fight["versions"][0]["confirmed_by"][0]["id"] == first.id

    assert first.points() == 1000
    assert first.profile()["stats"]["fights"] == 0
    assert first.get("/fights").json()["total"] == 0
    inbox = second.get("/fights/mine").json()
    assert [item["id"] for item in inbox["to_confirm"]] == [fight["id"]]

    confirmed = confirm(second, fight).json()
    assert confirmed["status"] == "confirmed"
    assert first.points() == 1020
    assert second.points() == 980
    assert first.get("/fights").json()["total"] == 1
    assert first.profile()["stats"]["wins"] == 1
    assert second.profile()["stats"]["losses"] == 1


def test_replayed_create_returns_same_fight(players):
    first, second = players(2)
    body = {**result_body(first.id), "opponent_id": second.id, "client_request_id": str(uuid.uuid4())}
    one = first.post("/fights", body)
    two = first.post("/fights", body)
    assert one.json()["id"] == two.json()["id"]
    assert len(second.get("/fights/mine").json()["to_confirm"]) == 1


def test_parallel_create_with_same_key_makes_one_fight(players):
    first, second = players(2)
    body = {**result_body(first.id), "opponent_id": second.id, "client_request_id": str(uuid.uuid4())}
    clones = [first.login for _ in range(8)]
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: first.post("/fights", body), clones))
    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["id"] for response in responses}) == 1
    assert len(second.get("/fights/mine").json()["to_confirm"]) == 1


def test_repeated_confirmation_counts_once(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    assert confirm(second, fight).status_code == 200
    assert confirm(second, fight).status_code == 200
    assert confirm(first, fight).status_code == 200
    assert first.points() == 1020
    assert second.points() == 980
    assert first.profile()["stats"]["fights"] == 1


def test_parallel_confirmations_give_one_result(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    with ThreadPoolExecutor(10) as pool:
        responses = list(pool.map(lambda _: confirm(second, fight), range(10)))
    assert {response.status_code for response in responses} == {200}
    assert first.points() == 1020
    assert second.points() == 980
    detail = first.get(f"/fights/{fight['id']}").json()
    assert len(detail["rating_changes"]) == 2


def test_only_participant_can_confirm_even_staff(owner, players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    assert confirm(owner, fight).status_code == 403
    assert first.get(f"/fights/{fight['id']}").json()["status"] == "pending"


def test_initiator_confirmation_alone_does_not_finalize(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    assert confirm(first, fight).status_code == 200
    assert first.get(f"/fights/{fight['id']}").json()["status"] == "pending"
    assert first.points() == 1000


def test_dispute_then_correction_voids_old_confirmations(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()

    disputed = second.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Победил я"})
    assert disputed.status_code == 200
    assert disputed.json()["status"] == "disputed"
    assert disputed.json()["can_correct"] is False
    assert first.get(f"/fights/{fight['id']}").json()["can_correct"] is True

    stale_confirm = second.post(f"/fights/{fight['id']}/confirm", {"version_no": 1})
    assert stale_confirm.status_code == 409

    corrected = first.post(
        f"/fights/{fight['id']}/correct", {**result_body(second.id), "expected_version": 1}
    )
    assert corrected.status_code == 200
    data = corrected.json()
    assert data["version_no"] == 2
    assert data["status"] == "pending"
    assert [item["id"] for item in data["versions"][1]["confirmed_by"]] == [first.id]
    assert data["versions"][0]["dispute_reason"] == "Победил я"

    assert second.post(f"/fights/{fight['id']}/confirm", {"version_no": 1}).status_code == 409
    assert first.points() == 1000

    final = second.post(f"/fights/{fight['id']}/confirm", {"version_no": 2})
    assert final.json()["status"] == "confirmed"
    assert first.points() == 980
    assert second.points() == 1020


def test_correction_rules(players):
    first, second, outsider = players(3)
    fight = create_fight(first, second, first).json()
    url = f"/fights/{fight['id']}/correct"
    body = {**result_body(second.id), "expected_version": 1}
    assert first.post(url, body).status_code == 409
    second.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Ошибка"})
    assert second.post(url, body).status_code == 403
    assert outsider.post(url, body).status_code == 403
    assert first.post(url, {**body, "winner_id": outsider.id}).status_code == 400
    assert first.post(url, body).status_code == 200
    replay = first.post(url, body)
    assert replay.status_code == 200
    assert replay.json()["version_no"] == 2


def test_author_cannot_dispute_own_version(players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    assert first.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Нет"}).status_code == 403


def test_validation_of_pair_and_winner(players):
    first, second, third = players(3)
    assert create_fight(first, first, first).status_code == 400
    assert create_fight(first, second, third).status_code == 400
    future = FIGHT_TIME.replace(year=2099)
    assert create_fight(first, second, first, future).status_code == 400


def test_unconfirmed_fight_hidden_from_outsiders(players):
    first, second, outsider = players(3)
    fight = create_fight(first, second, first).json()
    assert outsider.get(f"/fights/{fight['id']}").status_code == 403
    confirm(second, fight)
    assert outsider.get(f"/fights/{fight['id']}").status_code == 200


def test_statistics_streak_and_rivals(players):
    me, rival_a, rival_b, rival_c = players(4)
    moments = [FIGHT_TIME + timedelta(hours=hour) for hour in range(10)]
    play(me, rival_a, me, moments[0])
    play(me, rival_b, me, moments[1])
    play(me, rival_c, me, moments[2])
    play(me, rival_a, rival_a, moments[3])
    play(me, rival_b, me, moments[4])
    play(me, rival_a, rival_a, moments[5])
    play(me, rival_b, rival_b, moments[6])
    play(me, rival_b, rival_b, moments[7])
    stats = me.profile()["stats"]
    assert stats["fights"] == 8
    assert stats["wins"] == 4
    assert stats["losses"] == 4
    assert stats["win_rate"] == 50.0
    assert stats["best_streak"] == 3
    assert sorted(item["player"]["id"] for item in stats["nemeses"]) == sorted([rival_a.id, rival_b.id])
    assert {item["count"] for item in stats["nemeses"]} == {2}
    assert [item["player"]["id"] for item in stats["victims"]] == [rival_b.id]
    assert stats["victims"][0]["count"] == 2


def test_streak_uses_fight_time_not_insertion_order(players):
    me, rival = players(2)
    play(me, rival, me, FIGHT_TIME + timedelta(hours=1))
    play(me, rival, rival, FIGHT_TIME + timedelta(hours=2))
    play(me, rival, me, FIGHT_TIME)
    assert me.profile()["stats"]["best_streak"] == 2


def test_empty_statistics(players):
    stats = players(1)[0].profile()["stats"]
    assert stats["fights"] == 0
    assert stats["win_rate"] is None
    assert stats["nemeses"] == []
    assert stats["victims"] == []


def test_profile_history_lists_player_fights_newest_first(players):
    first, second, third = players(3)
    older = play(first, second, first, FIGHT_TIME)
    newer = play(second, first, second, FIGHT_TIME + timedelta(hours=1))
    play(second, third, second, FIGHT_TIME + timedelta(hours=2))
    rows = first.get(f"/players/{first.id}/fights").json()
    assert [row["id"] for row in rows] == [newer["id"], older["id"]]
    assert rows[1]["winner_id"] == first.id
    assert rows[1]["kind"] == "regular"
    assert rows[1]["points_change"] == [20, -20]
    assert rows[1]["player2"]["id"] == second.id


def test_future_tolerance_allows_now(players):
    from datetime import UTC, datetime

    first, second = players(2)
    response = first.post(
        "/fights",
        {
            "fought_at": iso(datetime.now(UTC)),
            "winner_id": first.id,
            "opponent_id": second.id,
            "client_request_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201
