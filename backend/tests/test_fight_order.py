"""Порядок боёв: подтверждение только по порядку, без боёв задним числом, решения админа по зависшим."""

from datetime import timedelta

from tests.conftest import FIGHT_TIME, confirm, create_fight, play, result_body
from tests.test_belts import schedule


def at(hours: int):
    return FIGHT_TIME + timedelta(hours=hours)


def test_later_fight_waits_for_earlier_open_fight_of_a_participant(players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(c, a, c, at(2)).json()

    blocked = confirm(a, late)
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert f"бой #{early['id']}" in detail and "Ждём: player2" in detail

    assert confirm(b, early).status_code == 200
    assert confirm(a, late).status_code == 200


def test_unrelated_players_are_not_blocked(players):
    a, b, c, d = players(4)
    create_fight(a, b, a, at(1))
    later = create_fight(c, d, c, at(2)).json()
    assert confirm(d, later).status_code == 200


def test_same_time_fights_go_by_record_order(players):
    a, b = players(2)
    first = create_fight(a, b, a, at(1)).json()
    second = create_fight(a, b, b, at(1)).json()
    assert confirm(b, second).status_code == 409
    assert confirm(b, first).status_code == 200
    assert confirm(b, second).status_code == 200


def test_disputed_fight_blocks_until_corrected(players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(a, c, a, at(2)).json()
    assert b.post(f"/fights/{early['id']}/dispute", {"version_no": 1, "reason": "Не так"}).status_code == 200
    blocked = confirm(c, late)
    assert blocked.status_code == 409
    # По оспоренному бою ход за автором записи: он должен исправить.
    assert "Ждём: player1" in blocked.json()["detail"]


def test_backdated_fight_cannot_be_recorded(players):
    a, b, c = players(3)
    play(a, b, a, at(5))
    response = create_fight(a, c, a, at(4))
    assert response.status_code == 400
    assert "задним числом" in response.json()["detail"]
    # Ровно в то же время или позже — можно; у других игроков свои даты.
    assert create_fight(a, c, a, at(5)).status_code == 201
    assert create_fight(c, b, c, at(5)).status_code == 201


def test_correction_cannot_move_fight_into_the_past(players):
    a, b, c = players(3)
    play(a, c, a, at(3))
    fight = create_fight(a, b, a, at(4)).json()
    assert b.post(f"/fights/{fight['id']}/dispute", {"version_no": 1, "reason": "Дата"}).status_code == 200
    url = f"/fights/{fight['id']}/correct"
    assert a.post(url, {**result_body(a.id, at(2)), "expected_version": 1}).status_code == 400
    assert a.post(url, {**result_body(a.id, at(3)), "expected_version": 1}).status_code == 200


def test_my_fights_show_blocker_and_blocking_banner(players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(c, a, c, at(2)).json()

    inbox = a.get("/fights/mine").json()
    blocked = next(item for item in inbox["to_confirm"] if item["id"] == late["id"])
    assert blocked["blocked_by"]["fight_id"] == early["id"]
    assert [player["id"] for player in blocked["blocked_by"]["waiting_for"]] == [b.id]
    assert inbox["blocking"] == []

    banner = b.get("/fights/mine").json()["blocking"]
    assert [item["fight"]["id"] for item in banner] == [early["id"]]
    assert sorted(player["id"] for player in banner[0]["delayed_players"]) == sorted([a.id, c.id])
    assert banner[0]["delayed_fights"] == 1

    assert confirm(b, early).status_code == 200
    assert b.get("/fights/mine").json()["blocking"] == []
    assert a.get(f"/fights/{late['id']}").json()["blocked_by"] is None


def test_admin_sees_open_fights_and_can_accept_in_order(admin, players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    late = create_fight(a, c, a, at(2)).json()

    rows = admin.get("/admin/fights/open").json()
    assert [row["id"] for row in rows] == [early["id"], late["id"]]
    assert rows[0]["blocks_count"] == 1 and rows[0]["blocked_by"] is None
    assert [player["id"] for player in rows[0]["waiting_for"]] == [b.id]
    assert rows[1]["blocked_by"]["fight_id"] == early["id"]

    assert admin.post(f"/admin/fights/{late['id']}/accept", {}).status_code == 409
    accepted = admin.post(f"/admin/fights/{early['id']}/accept", {"reason": "Соперник пропал"})
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "confirmed"
    assert body["resolution"]["accepted"] is True and body["resolution"]["by"]["id"] == admin.id
    assert a.points() > 1000
    assert confirm(c, late).status_code == 200


def test_admin_cancel_unblocks_and_frees_title_fight(admin, players):
    a, b, c = players(3)
    title = schedule(admin, b, a).json()
    stuck = a.post(f"/title-fights/{title['id']}/result", result_body(a.id, at(1))).json()
    later = create_fight(a, c, a, at(2)).json()
    assert confirm(c, later).status_code == 409

    cancelled = admin.post(f"/admin/fights/{stuck['id']}/cancel", {"reason": "Бой не состоялся"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["resolution"]["accepted"] is False
    assert confirm(c, later).status_code == 200

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


def test_legacy_backdated_open_fight_can_only_be_cancelled(admin, players):
    from app.db import SessionLocal
    from app.models import Fight

    a, b, c = players(3)
    play(a, c, a, at(2))
    stuck = create_fight(a, b, a, at(3)).json()
    # До запрета такой бой мог остаться: подтверждён более поздний бой, а ранний ещё без итога.
    with SessionLocal() as db:
        db.query(Fight).filter(Fight.id == stuck["id"]).update({Fight.fought_at: at(0)})
        db.commit()

    card = next(item for item in b.get("/fights/mine").json()["to_confirm"] if item["id"] == stuck["id"])
    assert card["backdated"]["player"]["id"] == a.id
    refused = confirm(b, stuck)
    assert refused.status_code == 409 and "Оспорить" in refused.json()["detail"]

    row = next(item for item in admin.get("/admin/fights/open").json() if item["id"] == stuck["id"])
    assert row["backdated"] is not None
    assert admin.post(f"/admin/fights/{stuck['id']}/accept", {}).status_code == 409
    assert admin.post(f"/admin/fights/{stuck['id']}/cancel", {"reason": "Старый бой"}).status_code == 200
