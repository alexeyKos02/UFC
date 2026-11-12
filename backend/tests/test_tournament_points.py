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


def test_tournament_fights_change_points_and_count_in_stats(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=25)
    state = run_tournament_start(admin, tournament["id"], apis)

    fight = play_match(by_id, playable_matches(state)[0])

    assert fight["status"] == "confirmed"
    winner = by_id[fight["winner_id"]]
    loser = by_id[fight["player1"]["id"] if fight["player2"]["id"] == winner.id else fight["player2"]["id"]]
    assert (winner.points(), loser.points()) == (1024, 982)
    assert fight["points_change"] is not None
    assert winner.profile()["stats"]["wins"] == 1
    assert loser.profile()["stats"]["losses"] == 1


def elo_only(apis) -> dict[int, int]:
    """Очки после турнира без приза: сумма начислений по боям."""
    totals = {}
    for api in apis:
        fights = api.get(f"/players/{api.id}/fights").json()
        totals[api.id] = 1000 + sum(
            change for fight in fights for change in [fight["points_change"][0 if fight["player1"]["id"] == api.id else 1]]
        )
    return totals


def test_tournament_winner_gets_prize_on_top_of_elo(admin, players):
    apis = players(4)
    tournament = new_tournament(admin, capacity=4, win_points=25)
    run_tournament_start(admin, tournament["id"], apis)
    finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    from_fights = elo_only(apis)
    assert apis[0].points() == from_fights[apis[0].id] + 25
    assert [api.points() for api in apis[1:]] == [from_fights[api.id] for api in apis[1:]]


def test_tournament_with_zero_points_gives_only_elo(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2, win_points=0)
    run_tournament_start(admin, tournament["id"], apis)
    finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    assert [api.points() for api in apis] == [1024, 982]


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
    assert first.points() == 1024 + 30
    assert second.points() == 982


def test_win_points_are_required_and_not_negative(admin):
    belt = new_belt(admin)
    body = {"title": "Кубок", "capacity": 2, "belt_id": belt["id"]}
    assert admin.post("/admin/tournaments", body).status_code == 422
    assert admin.post("/admin/tournaments", {**body, "win_points": -1}).status_code == 422
    created = admin.post("/admin/tournaments", {**body, "win_points": 15})
    assert created.status_code == 201
    assert created.json()["win_points"] == 15


def test_win_points_can_change_until_tournament_ends(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2, win_points=10)
    url = f"/admin/tournaments/{tournament['id']}"
    body = {"title": "Кубок", "capacity": 2, "belt_id": tournament["belt"]["id"]}
    run_tournament_start(admin, tournament["id"], apis)

    updated = admin.patch(url, {**body, "win_points": 40})
    assert updated.status_code == 200
    assert updated.json()["win_points"] == 40

    finish_tournament(admin, apis, tournament["id"], champion=apis[0])
    assert apis[0].points() == 1024 + 40
    assert admin.patch(url, {**body, "win_points": 50}).status_code == 409
    assert tournament_state(admin, tournament["id"])["win_points"] == 40


def test_tournament_upset_can_be_adjusted_manually(admin, players):
    from tests.conftest import ladder

    apis = players(4)
    ladder(apis)
    top, bottom = apis[0], apis[3]
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=2)
    state = run_tournament_start(admin, tournament["id"], [top, bottom])
    fight = play_match(by_id, playable_matches(state)[0], winner_id=bottom.id)

    assert fight["id"] in [row["fight_id"] for row in admin.get("/admin/rating/upsets").json()]
    response = admin.put(
        f"/admin/rating/adjustments/{fight['id']}",
        {"player_id": bottom.id, "points": 2, "reason": "Апсет", "expected_version": 0},
    )
    assert response.status_code == 200
