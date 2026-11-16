"""Техническая победа в турнире: соперник не явился, победителя назначает админ."""

from tests.conftest import (
    finish_tournament,
    new_tournament,
    play_match,
    playable_matches,
    result_body,
    run_tournament_start,
    tournament_state,
)
from tests.test_tournament_points import body_of


def walkover(staff, match: dict, winner_id: int, reason: str = "Не явился"):
    return staff.post(f"/admin/tournaments/matches/{match['id']}/walkover", {"winner_id": winner_id, "reason": reason})


def find(state: dict, match_id: int) -> dict:
    return next(match for rnd in state["rounds"] for match in rnd["matches"] if match["id"] == match_id)


def test_walkover_advances_winner_without_a_fight(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=40)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    assert match["can_walkover"] is True
    # Обычный участник кнопку не видит.
    assert find(tournament_state(apis[0], tournament["id"]), match["id"])["can_walkover"] is False

    winner_id = match["player2"]["id"]
    response = walkover(admin, match, winner_id)
    assert response.status_code == 200, response.text
    state = response.json()
    done = find(state, match["id"])
    assert (done["state"], done["winner_id"], done["is_walkover"]) == ("walkover", winner_id, True)
    final = next(m for m in state["rounds"][-1]["matches"] if not m["is_third_place"])
    assert winner_id in [seat["id"] for seat in (final["player1"], final["player2"]) if seat]

    # Боя нет: ни статистики, ни истории, ни очков.
    for api in apis:
        assert api.profile()["stats"]["all"]["fights"] == 0
        assert api.get(f"/players/{api.id}/fights").json() == []
        assert api.points() == 1000
    # Повтор с тем же победителем ничего не меняет, другой участник матча — конфликт.
    assert walkover(admin, match, winner_id).status_code == 200
    assert walkover(admin, match, match["player1"]["id"]).status_code == 409
    assert by_id[winner_id].post(f"/admin/tournaments/matches/{match['id']}/walkover/cancel").status_code == 403


def test_only_staff_and_never_in_final(admin, players):
    apis = players(2)
    tournament = new_tournament(admin, capacity=2)
    state = run_tournament_start(admin, tournament["id"], apis)
    final = playable_matches(state)[0]
    assert final["can_walkover"] is False
    assert walkover(apis[0], final, apis[0].id).status_code == 403
    assert walkover(admin, final, apis[0].id).status_code == 409


def test_walkover_cancels_unconfirmed_result(admin, players):
    apis = players(4)
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    by_id = {api.id: api for api in apis}
    submitter = by_id[match["player1"]["id"]]
    fight = submitter.post(f"/tournaments/matches/{match['id']}/result", result_body(submitter.id)).json()
    assert walkover(admin, match, match["player2"]["id"]).status_code == 200
    assert submitter.get(f"/fights/{fight['id']}").json()["status"] == "cancelled"


def test_cancel_walkover_reopens_match_until_next_round_is_played(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    first, second = playable_matches(state)
    walkover(admin, first, first["player1"]["id"])

    cancelled = admin.post(f"/admin/tournaments/matches/{first['id']}/walkover/cancel")
    assert cancelled.status_code == 200, cancelled.text
    reopened = find(cancelled.json(), first["id"])
    assert (reopened["state"], reopened["winner_id"], reopened["is_walkover"]) == ("ready", None, False)

    # Победитель прошёл дальше и сыграл финал — отменить уже нельзя.
    walkover(admin, first, first["player1"]["id"])
    play_match(by_id, second)
    final = next(m for m in tournament_state(admin, tournament["id"])["rounds"][-1]["matches"] if not m["is_third_place"])
    play_match(by_id, final)
    assert admin.post(f"/admin/tournaments/matches/{first['id']}/walkover/cancel").status_code == 409


def test_walkover_loser_gets_no_shared_third_place_prize(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=50)
    admin.patch(
        f"/admin/tournaments/{tournament['id']}",
        body_of(tournament, second_points=20, third_points=10, has_third_place=False),
    )
    state = run_tournament_start(admin, tournament["id"], apis)
    first, second = playable_matches(state)
    no_show = first["player2"]["id"]
    walkover(admin, first, first["player1"]["id"])
    second_fight = play_match(by_id, second)
    second_loser = second["player1"]["id"] if second_fight["winner_id"] == second["player2"]["id"] else second["player2"]["id"]
    finish_tournament(admin, apis, tournament["id"])

    assert by_id[no_show].points() == 1000
    assert by_id[second_loser].points() == 1010


def test_third_place_walkover_finishes_tournament_with_prizes(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    tournament = new_tournament(admin, capacity=4, win_points=50)
    admin.patch(f"/admin/tournaments/{tournament['id']}", body_of(tournament, second_points=20, third_points=10))
    state = run_tournament_start(admin, tournament["id"], apis)
    for match in playable_matches(state):
        play_match(by_id, match)
    state = tournament_state(admin, tournament["id"])
    final = next(m for m in state["rounds"][-1]["matches"] if not m["is_third_place"])
    third = next(m for m in state["rounds"][-1]["matches"] if m["is_third_place"])
    play_match(by_id, final)
    assert tournament_state(admin, tournament["id"])["status"] == "in_progress"

    response = walkover(admin, third, third["player1"]["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "finished"
    assert by_id[third["player1"]["id"]].points() == 1010
    assert by_id[third["player2"]["id"]].points() == 1000

    champion = by_id[final["player1"]["id"]] if by_id[final["player1"]["id"]].points() == 1050 else by_id[final["player2"]["id"]]
    assert champion.points() == 1050

    # Отмена технической победы снова открывает турнир: призы снимаются, пока он не завершится.
    reopened = admin.post(f"/admin/tournaments/matches/{third['id']}/walkover/cancel").json()
    assert reopened["status"] == "in_progress"
    assert all(api.points() == 1000 for api in apis)


def test_walkover_needs_known_pair_and_valid_winner(admin, players):
    *apis, outsider = players(5)
    tournament = new_tournament(admin, capacity=4)
    state = run_tournament_start(admin, tournament["id"], apis)
    match = playable_matches(state)[0]
    assert walkover(admin, match, outsider.id).status_code == 400
    final = next(m for m in state["rounds"][-1]["matches"] if not m["is_third_place"])
    assert walkover(admin, final, apis[0].id).status_code == 409
