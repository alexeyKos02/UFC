from concurrent.futures import ThreadPoolExecutor

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


def body_of(tournament: dict, **changes) -> dict:
    return {
        "title": tournament["title"],
        "capacity": tournament["capacity"],
        "belt_id": tournament["belt"]["id"],
        "win_points": tournament["win_points"],
        "second_points": tournament["second_points"],
        "third_points": tournament["third_points"],
        "has_third_place": tournament["has_third_place"],
        **changes,
    }


def places(state: dict) -> dict[str, int | None]:
    """Кто занял какое место по сетке: финал, матч за 3-е место (если есть)."""
    last = state["rounds"][-1]["matches"]
    final = next(match for match in last if not match["is_third_place"])
    third = next((match for match in last if match["is_third_place"]), None)
    pair = {final["player1"]["id"], final["player2"]["id"]}
    result = {"first": final["winner_id"], "second": (pair - {final["winner_id"]}).pop()}
    if third is not None:
        result["third"] = third["winner_id"]
        seats = {seat["id"] for seat in (third["player1"], third["player2"]) if seat}
        result["fourth"] = (seats - {third["winner_id"]}).pop() if len(seats) == 2 else None
    return result


def test_tournament_fights_give_no_league_points_and_count_as_tournament_stats(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=25)
    state = run_tournament_start(admin, tournament["id"], apis)

    fight = play_match(by_id, playable_matches(state)[0])

    assert fight["status"] == "confirmed"
    winner = by_id[fight["winner_id"]]
    loser = by_id[fight["player1"]["id"] if fight["player2"]["id"] == winner.id else fight["player2"]["id"]]
    assert (winner.points(), loser.points()) == (1000, 1000)
    assert fight["points_change"] is None
    stats = winner.profile()["stats"]
    assert (stats["all"]["wins"], stats["tournament"]["wins"], stats["league"]["wins"]) == (1, 1, 0)
    assert loser.profile()["stats"]["tournament"]["losses"] == 1
    assert winner.get(f"/players/{winner.id}/rating-history").json()["points"] == []


def test_prizes_for_first_three_places_with_third_place_match(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=50)
    assert tournament["has_third_place"] is True
    admin.patch(f"/admin/tournaments/{tournament['id']}", body_of(tournament, second_points=20, third_points=10))
    run_tournament_start(admin, tournament["id"], apis)
    state = finish_tournament(admin, apis, tournament["id"], champion=apis[0])

    place = places(state)
    assert place["first"] == apis[0].id
    assert {player: by_id[player].points() for player in place.values()} == {
        place["first"]: 1050,
        place["second"]: 1020,
        place["third"]: 1010,
        place["fourth"]: 1000,
    }


def test_without_third_place_match_both_semifinal_losers_share_third(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=50)
    admin.patch(
        f"/admin/tournaments/{tournament['id']}",
        body_of(tournament, second_points=20, third_points=10, has_third_place=False),
    )
    run_tournament_start(admin, tournament["id"], apis)
    state = finish_tournament(admin, apis, tournament["id"])
    assert all(not match["is_third_place"] for rnd in state["rounds"] for match in rnd["matches"])
    place = places(state)
    others = set(by_id) - {place["first"], place["second"]}
    assert by_id[place["first"]].points() == 1050
    assert by_id[place["second"]].points() == 1020
    assert {by_id[player].points() for player in others} == {1010}


def test_three_players_lone_semifinal_loser_takes_third_without_fight(admin, players):
    apis = players(3)
    tournament = new_tournament(admin, capacity=4, win_points=30)
    admin.patch(f"/admin/tournaments/{tournament['id']}", body_of(tournament, third_points=5))
    run_tournament_start(admin, tournament["id"], apis)
    state = finish_tournament(admin, apis, tournament["id"])
    third = next(match for match in state["rounds"][-1]["matches"] if match["is_third_place"])
    assert third["is_bye"] and third["winner_id"] is not None
    assert next(api for api in apis if api.id == third["winner_id"]).points() == 1005


def test_two_player_tournament_has_no_third_place(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2, win_points=0)
    assert tournament["has_third_place"] is False
    run_tournament_start(admin, tournament["id"], apis)
    finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    assert [api.points() for api in apis] == [1000, 1000]


def test_third_place_match_can_be_switched_on_in_running_tournament(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=40)
    url = f"/admin/tournaments/{tournament['id']}"
    admin.patch(url, body_of(tournament, has_third_place=False))
    state = run_tournament_start(admin, tournament["id"], apis)
    for match in playable_matches(state):
        play_match(by_id, match)

    switched = admin.patch(url, body_of(tournament, has_third_place=True, third_points=8))
    assert switched.status_code == 200, switched.text
    state = tournament_state(admin, tournament["id"])
    third = next(match for match in state["rounds"][-1]["matches"] if match["is_third_place"])
    assert third["state"] == "ready" and third["round_name"] == "Матч за 3-е место"

    # Бой за 3-е место записан — галочку уже не снять.
    by_id[third["player1"]["id"]].post(f"/tournaments/matches/{third['id']}/result", result_body(third["player1"]["id"]))
    assert admin.patch(url, body_of(tournament, has_third_place=False, third_points=8)).status_code == 409

    final = next(match for match in state["rounds"][-1]["matches"] if not match["is_third_place"])
    play_match(by_id, final)
    assert tournament_state(admin, tournament["id"])["status"] == "in_progress"


def test_cancelled_tournament_gives_no_prize(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2, win_points=25)
    run_tournament_start(admin, tournament["id"], apis)
    assert admin.post(f"/admin/tournaments/{tournament['id']}/cancel", {"reason": "Перенос"}).status_code == 200
    assert [api.points() for api in apis] == [1000, 1000]


def test_final_confirmation_awards_points_once(admin, players):
    apis = players(2)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=2, win_points=30)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    first = by_id[match["player1"]["id"]]
    second = by_id[match["player2"]["id"]]
    submitted = first.post(f"/tournaments/matches/{match['id']}/result", result_body(first.id)).json()

    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: confirm(second, submitted), range(8)))

    assert {response.status_code for response in responses} == {200}
    assert confirm(second, submitted).status_code == 200
    assert first.points() == 1030
    assert second.points() == 1000


def test_win_points_are_required_and_not_negative(admin):
    belt = new_belt(admin)
    body = {"title": "Кубок", "capacity": 2, "belt_id": belt["id"]}
    assert admin.post("/admin/tournaments", body).status_code == 422
    assert admin.post("/admin/tournaments", {**body, "win_points": -1}).status_code == 422
    assert admin.post("/admin/tournaments", {**body, "win_points": 5, "third_points": -1}).status_code == 422
    created = admin.post("/admin/tournaments", {**body, "win_points": 15})
    assert created.status_code == 201
    assert created.json()["win_points"] == 15


def test_prizes_can_change_until_tournament_ends(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2, win_points=10)
    url = f"/admin/tournaments/{tournament['id']}"
    run_tournament_start(admin, tournament["id"], apis)

    updated = admin.patch(url, body_of(tournament, win_points=40, second_points=15))
    assert updated.status_code == 200
    assert (updated.json()["win_points"], updated.json()["second_points"]) == (40, 15)

    finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    assert (apis[0].points(), apis[1].points()) == (1040, 1015)
    assert admin.patch(url, body_of(tournament, win_points=50, second_points=15)).status_code == 409
    assert tournament_state(admin, tournament["id"])["win_points"] == 40


def test_tournament_fights_are_not_upsets(admin, players):
    from tests.conftest import ladder

    apis = players(4)
    ladder(apis)
    top, bottom = apis[0], apis[3]
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=2)
    state = run_tournament_start(admin, tournament["id"], [top, bottom])
    fight = play_match(by_id, playable_matches(state)[0], winner_id=bottom.id)

    assert fight["id"] not in [row["fight_id"] for row in admin.get("/admin/rating/upsets").json()]
    response = admin.put(
        f"/admin/rating/adjustments/{fight['id']}",
        {"player_id": bottom.id, "points": 2, "reason": "Апсет", "expected_version": 0},
    )
    assert response.status_code == 409
