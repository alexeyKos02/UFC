"""Бои без итога: подтверждение в любом порядке и решения админа по зависшим боям."""

from datetime import timedelta

from tests.conftest import FIGHT_TIME, confirm, create_fight, play, result_body
from tests.test_belts import schedule


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
