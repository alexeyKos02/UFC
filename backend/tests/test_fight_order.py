"""Бои без итога: подтверждение в любом порядке и решения админа по зависшим боям."""

from datetime import timedelta

from tests.conftest import (
    FIGHT_TIME,
    confirm,
    create_fight,
    finish_tournament,
    new_belt,
    new_tournament,
    play,
    play_match,
    playable_matches,
    result_body,
    run_tournament_start,
    tournament_state,
)
from tests.test_belts import play_title, schedule


def at(hours: int):
    return FIGHT_TIME + timedelta(hours=hours)


def test_fights_can_be_confirmed_in_any_order(players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(c, a, c, at(2)).json()
    assert confirm(a, late).status_code == 200
    assert confirm(b, early).status_code == 200


def test_fight_can_be_recorded_with_an_earlier_date(players):
    a, b, c = players(3)
    play(a, b, a, at(5))
    assert create_fight(a, c, a, at(4)).status_code == 201


def test_my_fights_list_earlier_fights_first(players):
    a, b = players(2)
    late = create_fight(a, b, a, at(2)).json()
    early = create_fight(a, b, b, at(1)).json()
    assert [item["id"] for item in b.get("/fights/mine").json()["to_confirm"]] == [early["id"], late["id"]]


def test_admin_sees_open_fights_and_can_accept(admin, players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(a, c, a, at(2)).json()

    rows = admin.get("/admin/fights/open").json()
    assert [row["id"] for row in rows] == [early["id"], late["id"]]
    assert [player["id"] for player in rows[0]["waiting_for"]] == [b.id]

    accepted = admin.post(f"/admin/fights/{late['id']}/accept", {"reason": "Соперник пропал"})
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "confirmed"
    assert body["resolution"]["accepted"] is True and body["resolution"]["by"]["id"] == admin.id
    assert a.points() > 1000
    assert [row["id"] for row in admin.get("/admin/fights/open").json()] == [early["id"]]


def test_admin_cancel_frees_title_fight(admin, players):
    a, b = players(2)
    title = schedule(admin, b, a).json()
    stuck = a.post(f"/title-fights/{title['id']}/result", result_body(a.id, at(1))).json()

    cancelled = admin.post(f"/admin/fights/{stuck['id']}/cancel", {"reason": "Бой не состоялся"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["resolution"]["accepted"] is False

    # Титульный бой снова ждёт результата и попадает в предстоящие.
    assert any(item["kind"] == "title" for item in a.get("/fights/upcoming").json())
    again = a.post(f"/title-fights/{title['id']}/result", result_body(a.id, at(3)))
    assert again.status_code == 201
    assert again.json()["id"] != stuck["id"]


def test_only_staff_resolves_fights(players):
    a, b = players(2)
    fight = create_fight(a, b, a, at(1)).json()
    assert a.get("/admin/fights/open").status_code == 403
    assert a.post(f"/admin/fights/{fight['id']}/accept", {}).status_code == 403
    assert b.post(f"/admin/fights/{fight['id']}/cancel", {"reason": "abc"}).status_code == 403


def test_confirmed_fight_cannot_be_cancelled(admin, players):
    a, b = players(2)
    fight = play(a, b, a, at(1))
    assert admin.post(f"/admin/fights/{fight['id']}/cancel", {"reason": "Поздно"}).status_code == 409


# Удаление подтверждённых боёв админом


def test_admin_deletes_confirmed_fight_and_points_are_recalculated(admin, players):
    a, b, c = players(3)
    first = play(a, b, a, at(1))
    second = play(a, c, a, at(2))
    deleted = admin.post(f"/admin/fights/{first['id']}/delete", {"reason": "Записан по ошибке"})
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["status"] == "deleted"
    assert body["deletion"]["reason"] == "Записан по ошибке"
    assert body["rating_changes"] == []

    # Как будто первого боя не было: второй бой считается от стартовых очков.
    assert b.points() == 1000
    history = a.get(f"/players/{a.id}/rating-history").json()["points"]
    assert [item["fight_id"] for item in history] == [second["id"]]
    assert history[0]["points_before"] == 1000

    # Повтор — тот же ответ, неподтверждённый бой удалить нельзя.
    assert admin.post(f"/admin/fights/{first['id']}/delete", {"reason": "ещё раз"}).status_code == 200
    pending = create_fight(a, b, a, at(3)).json()
    assert admin.post(f"/admin/fights/{pending['id']}/delete", {"reason": "нельзя"}).status_code == 409
    assert b.post(f"/admin/fights/{second['id']}/delete", {"reason": "не админ"}).status_code == 403


def test_admin_search_finds_fights_by_players_and_date(admin, players):
    a, b, c = players(3)
    play(a, b, a, at(1))
    target = play(b, c, c, at(2))
    found = admin.get("/admin/fights/search", params={"player": c.user["nickname"]}).json()
    assert [item["id"] for item in found["items"]] == [target["id"]]
    pair = admin.get("/admin/fights/search", params={"player": b.user["nickname"], "opponent": a.user["nickname"]}).json()
    assert pair["total"] == 1 and pair["items"][0]["player1"]["id"] in (a.id, b.id)
    window = admin.get(
        "/admin/fights/search",
        params={"date_from": at(2).isoformat(), "date_to": (at(2) + timedelta(seconds=1)).isoformat()},
    ).json()
    assert [item["id"] for item in window["items"]] == [target["id"]]

    admin.post(f"/admin/fights/{target['id']}/delete", {"reason": "Проверка"})
    assert admin.get("/admin/fights/search", params={"player": c.user["nickname"]}).json()["total"] == 0
    gone = admin.get("/admin/fights/search", params={"player": c.user["nickname"], "state": "deleted"}).json()
    assert [item["id"] for item in gone["items"]] == [target["id"]]


def test_deleting_title_fight_returns_belt_and_reopens_it(admin, players):
    a, b, c = players(3)
    title = schedule(admin, b, a).json()
    won = play_title(title, a, b, a)
    assert admin.get("/belts").json()[0]["champion"]["id"] == a.id
    defense_title = schedule(admin, c).json()
    defense = play_title(defense_title, a, c, c)

    # Пояс после первого боя уже переходил: сначала удаляется более поздний бой.
    assert admin.post(f"/admin/fights/{won['id']}/delete", {"reason": "Ошибка"}).status_code == 409
    assert admin.post(f"/admin/fights/{defense['id']}/delete", {"reason": "Ошибка"}).status_code == 200
    belts = admin.get("/belts").json()
    assert belts[0]["champion"]["id"] == a.id
    reopened = admin.get("/admin/title-fights").json()
    assert next(item for item in reopened if item["id"] == defense_title["id"])["status"] == "scheduled"

    # Бой можно записать заново.
    again = c.post(f"/title-fights/{defense_title['id']}/result", result_body(c.id))
    assert again.status_code == 201, again.text
    assert again.json()["id"] != defense["id"]


def test_deleting_tournament_fights_reopens_bracket(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    belt = new_belt(admin, "Пояс сетки")
    tournament = new_tournament(admin, capacity=4, belt=belt, win_points=30)
    run_tournament_start(admin, tournament["id"], apis)

    first_round = playable_matches(tournament_state(admin, tournament["id"]))
    semi = play_match(by_id, first_round[0])
    winner = by_id[semi["winner_id"]]

    # Полуфинал удаляется: матч снова ждёт результата, победитель уходит из финала.
    assert admin.post(f"/admin/fights/{semi['id']}/delete", {"reason": "Переиграть"}).status_code == 200
    state = tournament_state(admin, tournament["id"])
    reopened = next(m for rnd in state["rounds"] for m in rnd["matches"] if m["id"] == first_round[0]["id"])
    assert reopened["state"] == "ready"
    final = state["rounds"][-1]["matches"][0]
    assert all((player or {}).get("id") != winner.id for player in (final["player1"], final["player2"]))

    # Доигрываем турнир; финал удаляется — турнир снова идёт, пояс и приз сняты.
    finished = finish_tournament(admin, apis, tournament["id"])
    champion = by_id[finished["winner"]["id"]]
    points_with_prize = champion.points()
    final_fight = finished["rounds"][-1]["matches"][0]["fight_id"]
    semi_fight = finished["rounds"][0]["matches"][0]["fight_id"]
    # Полуфинал удалить нельзя: его победитель уже сыграл финал.
    assert admin.post(f"/admin/fights/{semi_fight}/delete", {"reason": "Поздно"}).status_code == 409
    assert admin.post(f"/admin/fights/{final_fight}/delete", {"reason": "Ошибка"}).status_code == 200
    state = tournament_state(admin, tournament["id"])
    assert state["status"] == "in_progress" and state["winner"] is None
    assert admin.get(f"/belts/{belt['id']}").json()["champion"] is None
    assert champion.points() < points_with_prize - 30 + 1
