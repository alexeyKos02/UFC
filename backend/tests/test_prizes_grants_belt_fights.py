"""Призы турнира и ручные очки на графике профиля, бой за пояс с итогом от админа."""

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import PointGrant, TournamentPrizeChange
from app.services import recalc
from tests.conftest import confirm, finish_tournament, new_belt, new_tournament, play, result_body, run_tournament_start
from tests.test_recalc import stored
from tests.test_tournament_points import body_of, places


def history(api, player) -> list[dict]:
    response = api.get(f"/players/{player.id}/rating-history")
    assert response.status_code == 200, response.text
    return response.json()["points"]


def prize_rows() -> list[tuple]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                TournamentPrizeChange.fight_id,
                TournamentPrizeChange.player_id,
                TournamentPrizeChange.place,
                TournamentPrizeChange.points_before,
                TournamentPrizeChange.delta,
                TournamentPrizeChange.points_after,
                TournamentPrizeChange.table_place_before,
                TournamentPrizeChange.table_place_after,
                TournamentPrizeChange.champion_before,
                TournamentPrizeChange.champion_after,
            ).order_by(TournamentPrizeChange.fight_id, TournamentPrizeChange.player_id)
        ).all()
    return [tuple(row) for row in rows]


def grant_rows() -> list[tuple]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                PointGrant.id,
                PointGrant.points_before,
                PointGrant.points_after,
                PointGrant.table_place_before,
                PointGrant.table_place_after,
            ).order_by(PointGrant.id)
        ).all()
    return [tuple(row) for row in rows]


def finished_with_prizes(admin, apis, third_match=True) -> dict:
    tournament = new_tournament(admin, capacity=4, win_points=50)
    admin.patch(
        f"/admin/tournaments/{tournament['id']}",
        body_of(tournament, second_points=20, third_points=10, has_third_place=third_match),
    )
    run_tournament_start(admin, tournament["id"], apis)
    return finish_tournament(admin, apis, tournament["id"], champion=apis[0])


# Призы турнира на графике


def test_tournament_prizes_appear_in_rating_history(admin, players):
    apis = players(4)
    by_id = {api.id: api for api in apis}
    state = finished_with_prizes(admin, apis)
    place = places(state)

    for key, number, prize in (("first", 1, 50), ("second", 2, 20), ("third", 3, 10)):
        points = history(apis[0], by_id[place[key]])
        assert len(points) == 1
        item = points[0]
        assert item["event"] == "prize"
        assert item["tournament_place"] == number
        assert item["tournament"]["id"] == state["id"]
        assert (item["points_before"], item["delta"], item["points_after"]) == (1000, prize, 1000 + prize)
        assert item["table_place_after"] is not None
    # Четвёртое место призов не даёт и на графике ничего не появляется.
    assert history(apis[0], by_id[place["fourth"]]) == []
    # Победитель после приза — №1 в таблице.
    assert history(apis[0], by_id[place["first"]])[0]["table_place_after"] == 1


def test_prize_follows_league_fights_in_history(admin, players):
    apis = players(4)
    a, b = apis[0], apis[1]
    play(a, b, a)
    finished_with_prizes(admin, apis)
    points = history(a, a)
    assert [item["event"] for item in points] == ["fight", "prize"]
    assert points[1]["points_before"] == points[0]["points_after"]
    assert points[1]["points_after"] == a.points()


def test_deleting_closing_fight_removes_prizes_from_history(admin, players):
    apis = players(4)
    state = finished_with_prizes(admin, apis, third_match=False)
    final = next(match for match in state["rounds"][-1]["matches"] if not match["is_third_place"])
    assert prize_rows()
    deleted = admin.post(f"/admin/fights/{final['fight_id']}/delete", {"reason": "Ошибка в итоге"})
    assert deleted.status_code == 200, deleted.text
    assert prize_rows() == []
    assert all(history(admin, api) == [] for api in apis)


def test_prize_snapshots_match_full_recalculation(admin, players):
    apis = players(4)
    play(apis[2], apis[3], apis[2])
    finished_with_prizes(admin, apis)
    play(apis[0], apis[1], apis[1])
    live = (stored(), prize_rows())
    with engine.begin() as connection:
        recalc.recalculate(connection)
    assert (stored(), prize_rows()) == live


# Ручные очки


def test_staff_grants_and_takes_points_reason_only_for_staff(admin, players):
    a, b = players(2)
    play(a, b, a)
    before = a.points()
    b_before = b.points()
    granted = admin.post("/admin/rating/point-grants", {"player_id": b.id, "points": 40, "reason": "Лучший бой месяца"})
    assert granted.status_code == 201, granted.text
    assert granted.json()["points_before"] == b_before
    assert b.points() == granted.json()["points_after"] == granted.json()["points_before"] + 40

    taken = admin.post("/admin/rating/point-grants", {"player_id": a.id, "points": -15, "reason": "Неявка на бой"})
    assert taken.status_code == 201, taken.text
    assert a.points() == before - 15

    own = history(b, b)
    assert [item["event"] for item in own] == ["fight", "grant"]
    assert own[1]["delta"] == 40 and own[1]["reason"] is None
    assert own[1]["points_before"] == own[0]["points_after"]
    staff_view = history(admin, b)
    assert staff_view[1]["reason"] == "Лучший бой месяца"

    listed = admin.get("/admin/rating/point-grants").json()
    assert [item["delta"] for item in listed] == [-15, 40]


def test_grant_moves_player_up_the_table(admin, players):
    a, b = players(2)
    play(a, b, a)
    place = history(b, b)[0]["table_place_after"]
    admin.post("/admin/rating/point-grants", {"player_id": b.id, "points": 100, "reason": "Бонус за турнир"})
    grant = history(b, b)[-1]
    assert (grant["table_place_before"], grant["table_place_after"]) == (place, 1)
    assert place > 1


def test_cancel_grant_restores_points_and_replays_later_fights(admin, players):
    a, b = players(2)
    grant = admin.post("/admin/rating/point-grants", {"player_id": a.id, "points": 200, "reason": "Бонус"}).json()
    fight = play(a, b, a)
    with_bonus = a.points()
    cancelled = admin.post(f"/admin/rating/point-grants/{grant['id']}/cancel", {"reason": "Ошибка"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    # Без бонуса бой считается от 1000 у обоих.
    detail = a.get(f"/fights/{fight['id']}").json()
    change = next(item for item in detail["rating_changes"] if item["player"]["id"] == a.id)
    assert change["points_before"] == 1000
    assert a.points() == change["points_after"] < with_bonus
    assert [item["event"] for item in history(a, a)] == ["fight"]
    # Повторная отмена ничего не меняет.
    assert admin.post(f"/admin/rating/point-grants/{grant['id']}/cancel", {"reason": "Ещё раз"}).status_code == 200


def test_grant_snapshots_match_full_recalculation(admin, players):
    a, b, c = players(3)
    play(a, b, a)
    admin.post("/admin/rating/point-grants", {"player_id": c.id, "points": 30, "reason": "Бонус"})
    play(b, c, b)
    admin.post("/admin/rating/point-grants", {"player_id": a.id, "points": -20, "reason": "Штраф"})
    live = (stored(), grant_rows())
    with engine.begin() as connection:
        recalc.recalculate(connection)
    assert (stored(), grant_rows()) == live


def test_grant_validation_and_access(owner, admin, players):
    a, b = players(2)
    assert b.post("/admin/rating/point-grants", {"player_id": a.id, "points": 5, "reason": "Сам себе"}).status_code == 403
    assert admin.post("/admin/rating/point-grants", {"player_id": a.id, "points": 0, "reason": "Ноль"}).status_code == 400
    assert admin.post("/admin/rating/point-grants", {"player_id": a.id, "points": 5, "reason": ""}).status_code == 422
    assert admin.post("/admin/rating/point-grants", {"player_id": 999999, "points": 5, "reason": "Нет"}).status_code == 404
    assert owner.post("/admin/rating/point-grants", {"player_id": a.id, "points": 5, "reason": "Бонус"}).status_code == 201
    assert a.points() == 1005


# Бой за пояс на странице пояса


def test_admin_schedules_tournament_belt_fight_and_records_result(admin, players):
    a, b = players(2)
    belt = new_belt(admin, "Пояс легковесов")
    scheduled = admin.post("/admin/title-fights", {"belt_id": belt["id"], "player1_id": a.id, "player2_id": b.id})
    assert scheduled.status_code == 201, scheduled.text
    title_fight = scheduled.json()
    assert title_fight["belt"]["id"] == belt["id"]
    assert a.get(f"/belts/{belt['id']}").json()["open_title_fight"]["id"] == title_fight["id"]

    result = admin.post(
        f"/admin/title-fights/{title_fight['id']}/result", {**result_body(b.id), "method": "submission", "round": 2}
    )
    assert result.status_code == 200, result.text
    fight = result.json()
    assert fight["status"] == "confirmed" and fight["kind"] == "title"
    assert fight["winner_id"] == b.id
    detail = a.get(f"/belts/{belt['id']}").json()
    assert detail["champion"]["id"] == b.id
    assert detail["open_title_fight"] is None
    assert detail["history"][0]["fight_id"] == fight["id"]
    # Бой за пояс — бой лиги: очки Elo начислены.
    assert b.points() > 1000 > a.points()


def test_admin_result_replaces_unconfirmed_player_record(admin, players):
    a, b = players(2)
    belt = new_belt(admin)
    title_fight = admin.post(
        "/admin/title-fights", {"belt_id": belt["id"], "player1_id": a.id, "player2_id": b.id}
    ).json()
    submitted = a.post(f"/title-fights/{title_fight['id']}/result", result_body(a.id)).json()
    result = admin.post(f"/admin/title-fights/{title_fight['id']}/result", {**result_body(b.id), "reason": "Видео боя"})
    assert result.status_code == 200, result.text
    old = a.get(f"/fights/{submitted['id']}").json()
    assert old["status"] == "cancelled"
    assert confirm(b, submitted).status_code == 409
    assert a.get(f"/belts/{belt['id']}").json()["champion"]["id"] == b.id
    # Второй итог по закрытому назначению не вносится.
    again = admin.post(f"/admin/title-fights/{title_fight['id']}/result", result_body(a.id))
    assert again.status_code == 409


def test_one_open_fight_per_belt_and_belts_independent(admin, players):
    a, b, c = players(3)
    belt = new_belt(admin)
    body = {"belt_id": belt["id"], "player1_id": a.id, "player2_id": b.id}
    assert admin.post("/admin/title-fights", body).status_code == 201
    assert admin.post("/admin/title-fights", body).status_code == 409
    # Основной пояс независим от турнирного.
    assert admin.post("/admin/title-fights", {"player1_id": a.id, "player2_id": c.id}).status_code == 201
    # Пока назначен бой, этот пояс нельзя выдать без боя.
    assert admin.post(f"/admin/belts/{belt['id']}/award", {"player_id": c.id}).status_code == 409


def test_belt_fight_with_champion_needs_champion(admin, players):
    a, b, c = players(3)
    belt = new_belt(admin)
    admin.post(f"/admin/belts/{belt['id']}/award", {"player_id": a.id})
    wrong = admin.post("/admin/title-fights", {"belt_id": belt["id"], "player1_id": b.id, "player2_id": c.id})
    assert wrong.status_code == 409
    right = admin.post("/admin/title-fights", {"belt_id": belt["id"], "player2_id": b.id})
    assert right.status_code == 201
    title_fight = right.json()
    fight = admin.post(f"/admin/title-fights/{title_fight['id']}/result", result_body(a.id)).json()
    win = a.get(f"/belts/{belt['id']}").json()["history"][0]
    assert win["fight_id"] == fight["id"] and win["is_defense"] is True


def test_player_cannot_record_belt_fight_result_as_admin(admin, players):
    a, b = players(2)
    belt = new_belt(admin)
    title_fight = admin.post(
        "/admin/title-fights", {"belt_id": belt["id"], "player1_id": a.id, "player2_id": b.id}
    ).json()
    assert a.post(f"/admin/title-fights/{title_fight['id']}/result", result_body(a.id)).status_code == 403
    assert admin.post("/admin/title-fights/999999/result", result_body(a.id)).status_code == 404


# Очки за неосновной пояс, взятый в бою


def belt_with_points(admin, points: int = 30, name: str = "Пояс средневесов") -> dict:
    response = admin.post("/admin/belts", {"name": name, "title_points": points})
    assert response.status_code == 201, response.text
    assert response.json()["title_points"] == points
    return response.json()


def record_belt_fight(admin, belt: dict, player2, winner, player1=None, **extra):
    body = {**result_body(winner.id), "player2_id": player2.id, **extra}
    if player1 is not None:
        body["player1_id"] = player1.id
    return admin.post(f"/admin/belts/{belt['id']}/fights", body)


def change(fight: dict, player) -> dict:
    return next(item for item in fight["rating_changes"] if item["player"]["id"] == player.id)


def test_record_belt_fight_in_one_form_gives_belt_points(admin, players):
    a, b = players(2)
    belt = belt_with_points(admin, 30)
    response = record_belt_fight(admin, belt, b, a, player1=a, method="ko_tko", round=1)
    assert response.status_code == 201, response.text
    fight = response.json()
    assert fight["status"] == "confirmed" and fight["kind"] == "title"
    winner, loser = change(fight, a), change(fight, b)
    # Вакантный пояс: победитель +30 сверх Elo, проигравший пояса не терял — без штрафа.
    assert (winner["belt_delta"], loser["belt_delta"]) == (30, 0)
    assert winner["points_after"] == winner["points_before"] + winner["delta"] + 30
    assert a.points() == winner["points_after"]
    assert fight["points_change"] == [winner["delta"] + 30, loser["delta"]]
    assert a.get(f"/belts/{belt['id']}").json()["champion"]["id"] == a.id
    point = history(a, a)[-1]
    assert point["event"] == "fight" and point["belt_delta"] == 30 and point["belt"]["id"] == belt["id"]


def test_champion_losing_belt_loses_belt_points_and_defense_gives_half(admin, players):
    a, b, c = players(3)
    belt = belt_with_points(admin, 30)
    admin.post(f"/admin/belts/{belt['id']}/award", {"player_id": a.id})
    # Защита: чемпион +15 сверх Elo, претендент без штрафа за пояс.
    defense = record_belt_fight(admin, belt, b, a).json()
    assert (change(defense, a)["belt_delta"], change(defense, b)["belt_delta"]) == (15, 0)
    # Потеря: новый чемпион +30, прежний −30.
    loss = record_belt_fight(admin, belt, c, c).json()
    assert (change(loss, c)["belt_delta"], change(loss, a)["belt_delta"]) == (30, -30)
    assert change(loss, a)["points_after"] == change(loss, a)["points_before"] + change(loss, a)["delta"] - 30
    assert a.points() == change(loss, a)["points_after"]


def test_belt_points_are_fixed_when_fight_is_confirmed(admin, players):
    a, b = players(2)
    belt = belt_with_points(admin, 30)
    fight = record_belt_fight(admin, belt, b, a, player1=a).json()
    before = a.points()
    assert admin.patch(f"/admin/belts/{belt['id']}", {"name": belt["name"], "title_points": 80}).status_code == 200
    with engine.begin() as connection:
        recalc.recalculate(connection)
    assert a.points() == before
    assert change(a.get(f"/fights/{fight['id']}").json(), a)["belt_delta"] == 30


def test_belt_points_survive_full_recalculation_and_vanish_on_delete(admin, players):
    a, b, c = players(3)
    belt = belt_with_points(admin, 40)
    play(a, c, a)
    fight = record_belt_fight(admin, belt, b, b, player1=a).json()
    play(b, c, c)
    live = stored()
    with engine.begin() as connection:
        recalc.recalculate(connection)
    assert stored() == live
    deleted = admin.post(f"/admin/fights/{fight['id']}/delete", {"reason": "Ошибка"})
    assert deleted.status_code == 200, deleted.text
    with engine.begin() as connection:
        recalc.recalculate(connection)
    assert all(item.get("belt_delta", 0) == 0 for item in history(b, b))
    assert a.get(f"/belts/{belt['id']}").json()["champion"] is None


def test_no_belt_points_for_main_belt_tournament_or_manual_award(admin, players):
    apis = players(4)
    main = next(belt for belt in admin.get("/belts").json() if belt["kind"] == "main")
    assert admin.patch(f"/admin/belts/{main['id']}", {"name": main["name"], "title_points": 30}).status_code == 400
    belt = belt_with_points(admin, 30, "Турнирный пояс")
    tournament = new_tournament(admin, capacity=4, belt=belt, win_points=0)
    run_tournament_start(admin, tournament["id"], apis)
    finish_tournament(admin, apis, tournament["id"])
    admin.post(f"/admin/belts/{belt['id']}/award", {"player_id": apis[3].id})
    with SessionLocal() as db:
        from app.models import RatingChange

        assert db.scalar(select(RatingChange.id).where(RatingChange.belt_delta != 0)) is None


def test_record_belt_fight_validation(admin, players):
    a, b, c = players(3)
    belt = belt_with_points(admin, 30)
    assert record_belt_fight(admin, belt, b, c, player1=a).status_code == 400
    assert record_belt_fight(admin, belt, b, b).status_code == 400  # вакантный: нужен первый игрок
    admin.post("/admin/title-fights", {"belt_id": belt["id"], "player1_id": a.id, "player2_id": b.id})
    assert record_belt_fight(admin, belt, c, c, player1=a).status_code == 409
    assert b.post(f"/admin/belts/{belt['id']}/fights", {**result_body(b.id), "player2_id": b.id}).status_code == 403
