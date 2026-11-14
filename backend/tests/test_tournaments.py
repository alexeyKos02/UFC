from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.conftest import (
    confirm,
    finish_tournament,
    new_belt,
    new_tournament,
    play_match,
    playable_matches,
    result_body,
    run_tournament_start,
    tournament_state,
)


def test_player_joins_and_leaves_before_start(admin, players):
    player = players(1)[0]
    tournament = new_tournament(admin, capacity=4)
    joined = player.post(f"/tournaments/{tournament['id']}/join").json()
    assert joined["seats_taken"] == 1
    assert joined["is_participant"] is True
    assert player.post(f"/tournaments/{tournament['id']}/join").json()["seats_taken"] == 1
    left = player.post(f"/tournaments/{tournament['id']}/leave").json()
    assert left["seats_taken"] == 0


def test_draft_is_closed_for_players(admin, players):
    player = players(1)[0]
    tournament = new_tournament(admin, publish=False)
    assert player.post(f"/tournaments/{tournament['id']}/join").status_code == 409
    assert player.get(f"/tournaments/{tournament['id']}").status_code == 404
    assert tournament["id"] not in [item["id"] for item in player.get("/tournaments").json()]


def test_full_tournament_rejects_join(admin, players):
    apis = players(3)
    tournament = new_tournament(admin, capacity=2)
    assert apis[0].post(f"/tournaments/{tournament['id']}/join").status_code == 200
    assert apis[1].post(f"/tournaments/{tournament['id']}/join").status_code == 200
    assert apis[2].post(f"/tournaments/{tournament['id']}/join").status_code == 409


def test_parallel_joins_for_last_seat_admit_one(admin, players):
    apis = players(12)
    tournament = new_tournament(admin, capacity=5)
    for api in apis[:4]:
        api.post(f"/tournaments/{tournament['id']}/join")
    contenders = apis[4:]
    with ThreadPoolExecutor(len(contenders)) as pool:
        responses = list(pool.map(lambda api: api.post(f"/tournaments/{tournament['id']}/join"), contenders))
    codes = sorted(response.status_code for response in responses)
    assert codes.count(200) == 1
    assert codes.count(409) == len(contenders) - 1
    assert tournament_state(admin, tournament["id"])["seats_taken"] == 5


def test_start_needs_two_participants(admin, players):
    player = players(1)[0]
    tournament = new_tournament(admin)
    player.post(f"/tournaments/{tournament['id']}/join")
    assert admin.post(f"/admin/tournaments/{tournament['id']}/start").status_code == 409


def test_player_cannot_leave_after_start(admin, players):
    apis = players(2)
    tournament = new_tournament(admin)
    run_tournament_start(admin, tournament["id"], apis)
    assert apis[0].post(f"/tournaments/{tournament['id']}/leave").status_code == 409


@pytest.mark.parametrize(
    ("count", "rounds", "byes"),
    [(2, 1, 0), (3, 2, 1), (4, 2, 0), (5, 3, 3), (6, 3, 2), (7, 3, 1), (8, 3, 0)],
)
def test_bracket_shape_for_any_size(admin, players, count, rounds, byes):
    apis = players(count)
    tournament = new_tournament(admin, capacity=8)
    state = run_tournament_start(admin, tournament["id"], apis)
    assert len(state["rounds"]) == rounds
    first_round = state["rounds"][0]["matches"]
    assert sum(1 for match in first_round if match["is_bye"]) == byes
    seated = [
        player["id"]
        for match in first_round
        for player in (match["player1"], match["player2"])
        if player is not None
    ]
    assert sorted(seated) == sorted(api.id for api in apis)
    assert state["rounds"][-1]["name"] == "Финал"


def test_bye_is_not_a_fight_or_win(admin, players):
    apis = players(3)
    tournament = new_tournament(admin)
    state = run_tournament_start(admin, tournament["id"], apis)
    bye = next(match for match in state["rounds"][0]["matches"] if match["is_bye"])
    bye_player = next(api for api in apis if api.id == bye["player1"]["id"])
    assert bye["winner_id"] == bye_player.id
    assert bye["fight_id"] is None
    assert bye_player.profile()["stats"]["all"]["fights"] == 0
    assert bye_player.points() == 1000
    final = state["rounds"][1]["matches"][0]
    assert bye_player.id in [p["id"] for p in (final["player1"], final["player2"]) if p]


def test_repeated_start_keeps_single_bracket(admin, players):
    apis = players(5)
    tournament = new_tournament(admin)
    state = run_tournament_start(admin, tournament["id"], apis)
    again = admin.post(f"/admin/tournaments/{tournament['id']}/start")
    assert again.status_code == 200
    assert again.json()["rounds"] == state["rounds"]


def test_parallel_start_generates_bracket_once(admin, players):
    apis = players(6)
    tournament = new_tournament(admin)
    for api in apis:
        api.post(f"/tournaments/{tournament['id']}/join")
    with ThreadPoolExecutor(6) as pool:
        responses = list(
            pool.map(lambda _: admin.post(f"/admin/tournaments/{tournament['id']}/start"), range(6))
        )
    assert {response.status_code for response in responses} == {200}
    state = tournament_state(admin, tournament["id"])
    # 7 матчей сетки на 8 мест и матч за 3-е место.
    assert sum(len(rnd["matches"]) for rnd in state["rounds"]) == 8


def test_join_closed_after_start(admin, players):
    apis = players(3)
    tournament = new_tournament(admin)
    run_tournament_start(admin, tournament["id"], apis[:2])
    assert apis[2].post(f"/tournaments/{tournament['id']}/join").status_code == 409


def test_confirmed_result_advances_winner_once(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    first = by_id[match["player1"]["id"]]
    second = by_id[match["player2"]["id"]]

    submitted = first.post(f"/tournaments/matches/{match['id']}/result", result_body(first.id)).json()
    pending = tournament_state(admin, tournament["id"])
    final = pending["rounds"][1]["matches"][0]
    assert final["player1"] is None and final["player2"] is None

    assert confirm(second, submitted).status_code == 200
    assert confirm(second, submitted).status_code == 200

    after = tournament_state(admin, tournament["id"])
    final = after["rounds"][1]["matches"][0]
    seated = [player["id"] for player in (final["player1"], final["player2"]) if player]
    assert seated == [first.id]
    assert first.profile()["stats"]["all"]["wins"] == 1


def test_only_pair_can_submit_and_one_record_per_match(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    first = by_id[match["player1"]["id"]]
    second = by_id[match["player2"]["id"]]
    outsider = next(api for api in apis if api.id not in (first.id, second.id))
    url = f"/tournaments/matches/{match['id']}/result"

    assert outsider.post(url, result_body(first.id)).status_code == 403
    assert first.post(url, result_body(outsider.id)).status_code == 400
    one = first.post(url, result_body(first.id))
    assert one.status_code == 201
    replay = first.post(url, result_body(first.id))
    assert replay.status_code == 201
    assert replay.json()["id"] == one.json()["id"]
    assert second.post(url, result_body(second.id)).status_code == 409


def test_tournament_fight_dispute_keeps_single_record(admin, players):
    apis = players(2)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=2)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    first = by_id[match["player1"]["id"]]
    second = by_id[match["player2"]["id"]]
    fight = first.post(f"/tournaments/matches/{match['id']}/result", result_body(first.id)).json()
    second.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Неверно"})
    corrected = first.post(f"/fights/{fight['id']}/correct", {**result_body(second.id), "expected_version": 1}).json()
    assert corrected["id"] == fight["id"]
    confirmed = confirm(second, corrected).json()
    assert confirmed["status"] == "confirmed"
    finished = tournament_state(admin, tournament["id"])
    assert finished["status"] == "finished"
    assert finished["winner"]["id"] == second.id


def test_final_finishes_tournament_and_awards_belt(admin, players):
    apis = players(5)
    belt = new_belt(admin, "Золотой кулак")
    tournament = new_tournament(admin, capacity=8, belt=belt)
    run_tournament_start(admin, tournament["id"], apis)
    state = finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    assert state["status"] == "finished"
    assert state["winner"]["id"] == apis[0].id

    profile = apis[0].profile()
    assert profile["belts"]["active"][0]["caption"] == "Действующий чемпион"
    assert profile["belts"]["active"][0]["belt"]["name"] == "Золотой кулак"
    detail = admin.get(f"/belts/{belt['id']}").json()
    assert detail["champion"]["id"] == apis[0].id
    assert detail["history"][0]["tournament"]["id"] == tournament["id"]


def test_cancel_keeps_confirmed_fights_and_gives_no_belt(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    belt = new_belt(admin)
    tournament = new_tournament(admin, capacity=4, belt=belt)
    state = run_tournament_start(admin, tournament["id"], apis)
    ready = playable_matches(state)
    confirmed = play_match(by_id, ready[0])
    second_first = by_id[ready[1]["player1"]["id"]]
    second_other = by_id[ready[1]["player2"]["id"]]
    open_fight = second_first.post(
        f"/tournaments/matches/{ready[1]['id']}/result", result_body(second_first.id)
    ).json()

    assert admin.post(f"/admin/tournaments/{tournament['id']}/cancel", {"reason": "Нет игроков"}).status_code == 200
    state = tournament_state(admin, tournament["id"])
    assert state["status"] == "cancelled"
    assert state["cancel_reason"] == "Нет игроков"
    assert state["winner"] is None

    assert confirm(second_other, open_fight).status_code == 409
    assert second_other.points() == 1000
    assert admin.get(f"/fights/{confirmed['id']}").json()["status"] == "confirmed"
    assert admin.get(f"/belts/{belt['id']}").json()["champion"] is None


def test_cancel_requires_reason_and_finished_cannot_be_cancelled(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2)
    run_tournament_start(admin, tournament["id"], apis)
    assert admin.post(f"/admin/tournaments/{tournament['id']}/cancel", {"reason": ""}).status_code == 422
    finish_tournament(admin, apis, tournament["id"])
    assert admin.post(f"/admin/tournaments/{tournament['id']}/cancel", {"reason": "Поздно"}).status_code == 409


def test_one_running_tournament_per_belt(admin, players):
    belt = new_belt(admin)
    new_tournament(admin, belt=belt)
    second = new_tournament(admin, belt=belt, publish=False)
    assert admin.post(f"/admin/tournaments/{second['id']}/publish").status_code == 409


def test_belt_is_free_after_previous_tournament_cancelled(admin):
    belt = new_belt(admin)
    first = new_tournament(admin, belt=belt)
    admin.post(f"/admin/tournaments/{first['id']}/cancel", {"reason": "Перенос"})
    second = new_tournament(admin, belt=belt, publish=False)
    assert admin.post(f"/admin/tournaments/{second['id']}/publish").status_code == 200


def test_main_belt_cannot_be_used_for_tournament(admin):
    main = next(belt for belt in admin.get("/belts").json() if belt["kind"] == "main")
    response = admin.post(
        "/admin/tournaments", {"title": "T", "capacity": 2, "win_points": 0, "belt_id": main["id"]}
    )
    assert response.status_code == 400


def test_capacity_cannot_drop_below_participants(admin, players):
    apis = players(3)
    tournament = new_tournament(admin, capacity=4)
    for api in apis:
        api.post(f"/tournaments/{tournament['id']}/join")
    response = admin.patch(
        f"/admin/tournaments/{tournament['id']}",
        {"title": "T", "capacity": 2, "win_points": 10, "belt_id": tournament["belt"]["id"]},
    )
    assert response.status_code == 409


def test_blocked_player_frees_seat_before_start(owner, admin, players):
    first, second, third = players(3)
    tournament = new_tournament(admin, capacity=2)
    first.post(f"/tournaments/{tournament['id']}/join")
    second.post(f"/tournaments/{tournament['id']}/join")
    owner.post(f"/admin/users/{first.id}/block")
    assert tournament_state(admin, tournament["id"])["seats_taken"] == 1
    assert third.post(f"/tournaments/{tournament['id']}/join").status_code == 200
