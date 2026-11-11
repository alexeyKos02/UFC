from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from app.services.rating import elo_delta
from tests.conftest import (
    confirm,
    finish_tournament,
    new_belt,
    new_tournament,
    result_body,
    run_tournament_start,
)


def main_belt(api) -> dict:
    return next(belt for belt in api.get("/belts").json() if belt["kind"] == "main")


def win_tournament(admin, belt, apis, champion):
    tournament = new_tournament(admin, capacity=4, belt=belt)
    run_tournament_start(admin, tournament["id"], apis)
    return finish_tournament(admin, apis, tournament["id"], champion=champion)


def schedule(staff, player2, player1=None):
    body = {"player2_id": player2.id}
    if player1 is not None:
        body["player1_id"] = player1.id
    return staff.post("/admin/title-fights", body)


def play_title(title_fight, submitter, other, winner) -> dict:
    fight = submitter.post(f"/title-fights/{title_fight['id']}/result", result_body(winner.id)).json()
    response = confirm(other, fight)
    assert response.status_code == 200, response.text
    return response.json()


def test_tournament_belt_transfer_and_labels(admin, players):
    first, second, third, fourth = players(4)
    apis = [first, second, third, fourth]
    belt = new_belt(admin, "Стальной пояс")
    won = win_tournament(admin, belt, apis, first)

    champion_view = first.profile()["belts"]
    assert champion_view["active"][0]["caption"] == "Действующий чемпион"
    assert champion_view["past"] == []

    win_tournament(admin, belt, apis, second)
    old_champion = first.profile()["belts"]
    assert old_champion["active"] == []
    assert old_champion["past"][0]["caption"] == "Победитель турнира за пояс „Стальной пояс“"
    assert second.profile()["belts"]["active"][0]["belt"]["id"] == belt["id"]

    finished_page = admin.get(f"/tournaments/{won['id']}").json()
    assert finished_page["winner"]["id"] == first.id
    detail = admin.get(f"/belts/{belt['id']}").json()
    assert detail["champion"]["id"] == second.id
    assert len(detail["history"]) == 2


def test_repeat_win_keeps_champion_and_adds_history(admin, players):
    apis = players(4)
    belt = new_belt(admin)
    win_tournament(admin, belt, apis, apis[0])
    win_tournament(admin, belt, apis, apis[0])
    belts = apis[0].profile()["belts"]
    assert len(belts["active"]) == 1
    assert len(belts["active"][0]["wins"]) == 2
    assert belts["past"] == []
    history = admin.get(f"/belts/{belt['id']}").json()["history"]
    assert [item["is_defense"] for item in history] == [True, False]


def test_returned_belt_shows_one_active_icon_with_full_history(admin, players):
    apis = players(4)
    belt = new_belt(admin)
    win_tournament(admin, belt, apis, apis[0])
    win_tournament(admin, belt, apis, apis[1])
    win_tournament(admin, belt, apis, apis[0])
    belts = apis[0].profile()["belts"]
    assert len(belts["active"]) == 1
    assert belts["past"] == []
    assert len(belts["active"][0]["wins"]) == 2


def test_player_can_hold_several_belts(admin, players):
    apis = players(2)
    win_tournament(admin, new_belt(admin, "Первый"), apis, apis[0])
    win_tournament(admin, new_belt(admin, "Второй"), apis, apis[0])
    names = sorted(item["belt"]["name"] for item in apis[0].profile()["belts"]["active"])
    assert names == ["Второй", "Первый"]


def test_vacant_main_belt_title_fight(admin, players):
    first, second = players(2)
    response = schedule(admin, second, first)
    assert response.status_code == 201
    title_fight = response.json()
    assert title_fight["champion_id"] is None

    assert first.points() == 1000
    assert first.profile()["belts"]["active"] == []
    my_card = first.get("/fights/mine").json()["upcoming"][0]
    assert my_card["kind"] == "title"
    assert my_card["id"] == title_fight["id"]
    assert my_card["can_submit"] is True

    submitted = first.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).json()
    assert first.points() == 1000
    assert main_belt(first)["champion"] is None

    confirm(second, submitted)
    assert first.points() == 1020
    assert second.points() == 980
    belts = first.profile()["belts"]
    assert belts["active"][0]["belt"]["kind"] == "main"


def test_champion_defense_and_transfer(admin, players):
    champion, challenger, next_challenger = players(3)
    fight = schedule(admin, challenger, champion).json()
    play_title(fight, champion, challenger, champion)
    assert main_belt(admin)["champion"]["id"] == champion.id

    defense = schedule(admin, next_challenger).json()
    assert defense["player1"]["id"] == champion.id
    assert defense["champion_id"] == champion.id
    points_before, challenger_before = champion.points(), next_challenger.points()
    played = play_title(defense, next_challenger, champion, champion)
    assert played["is_title_defense"] is True
    assert champion.points() == points_before + elo_delta(points_before, challenger_before)
    assert main_belt(admin)["champion"]["id"] == champion.id
    history = admin.get(f"/belts/{main_belt(admin)['id']}").json()["history"]
    assert [item["is_defense"] for item in history] == [True, False]

    transfer = schedule(admin, challenger).json()
    played = play_title(transfer, challenger, champion, challenger)
    assert played["is_title_defense"] is False
    assert main_belt(admin)["champion"]["id"] == challenger.id
    old = champion.profile()["belts"]
    assert old["active"] == []
    assert old["past"][0]["caption"] == "Победитель титульного боя за пояс „Чемпион лиги“"
    assert len(old["past"][0]["wins"]) == 2


def test_champion_must_be_in_title_fight(admin, players):
    champion, challenger, outsider = players(3)
    play_title(schedule(admin, challenger, champion).json(), champion, challenger, champion)
    assert schedule(admin, challenger, outsider).status_code == 409


def test_vacant_belt_needs_two_different_players(admin, players):
    first = players(1)[0]
    assert schedule(admin, first).status_code == 400
    assert schedule(admin, first, first).status_code == 400


def test_title_fight_needs_active_players(owner, admin, players):
    first, second = players(2)
    owner.post(f"/admin/users/{second.id}/block")
    assert schedule(admin, second, first).status_code == 409


def test_only_one_open_title_fight(admin, players):
    first, second, third = players(3)
    assert schedule(admin, second, first).status_code == 201
    assert schedule(admin, third, first).status_code == 409


def test_parallel_scheduling_makes_one_title_fight(admin, players):
    first, second, *rest = players(8)
    with ThreadPoolExecutor(len(rest)) as pool:
        responses = list(pool.map(lambda api: schedule(admin, api, first), rest))
    codes = [response.status_code for response in responses]
    assert codes.count(201) == 1
    assert codes.count(409) == len(rest) - 1


def test_player_cannot_schedule_title_fight(players):
    first, second = players(2)
    assert schedule(first, second, first).status_code == 403


def test_cancel_closes_card_for_result_and_confirmation(admin, players):
    first, second = players(2)
    title_fight = schedule(admin, second, first).json()
    submitted = first.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).json()
    cancelled = admin.post(f"/admin/title-fights/{title_fight['id']}/cancel", {"reason": "Перенос"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert confirm(second, submitted).status_code == 409
    assert first.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).status_code == 409
    assert first.get("/fights/mine").json()["upcoming"] == []
    assert first.points() == 1000
    assert main_belt(admin)["champion"] is None


def test_cannot_cancel_confirmed_title_fight(admin, players):
    first, second = players(2)
    title_fight = schedule(admin, second, first).json()
    play_title(title_fight, first, second, first)
    response = admin.post(f"/admin/title-fights/{title_fight['id']}/cancel", {"reason": "Поздно"})
    assert response.status_code == 409
    assert main_belt(admin)["champion"]["id"] == first.id


def test_parallel_title_confirmation_awards_once(admin, players):
    first, second = players(2)
    title_fight = schedule(admin, second, first).json()
    submitted = first.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).json()
    with ThreadPoolExecutor(8) as pool:
        responses = list(pool.map(lambda _: confirm(second, submitted), range(8)))
    assert {response.status_code for response in responses} == {200}
    history = admin.get(f"/belts/{main_belt(admin)['id']}").json()["history"]
    assert len(history) == 1
    assert first.points() == 1020


def test_title_result_only_by_participant(admin, players):
    first, second, outsider = players(3)
    title_fight = schedule(admin, second, first).json()
    assert outsider.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).status_code == 403
    assert admin.post(f"/title-fights/{title_fight['id']}/result", result_body(first.id)).status_code == 403


def test_belt_rename_and_icon_for_all_belts(admin):
    main = main_belt(admin)
    renamed = admin.patch(f"/admin/belts/{main['id']}", {"name": "Король лиги"})
    assert renamed.json()["name"] == "Король лиги"
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (240, 200, 0)).save(buffer, format="PNG")
    icon = admin.post(f"/admin/belts/{main['id']}/icon", files={"file": ("i.png", buffer.getvalue(), "image/png")})
    assert icon.status_code == 200
    assert icon.json()["icon_url"]


def test_promos_three_types_and_visibility(admin, players):
    first, second = players(2)
    tournament = new_tournament(admin)
    now = datetime.now(UTC).replace(year=2026, month=1, day=1)
    tournament_promo = admin.post(
        "/admin/promos", {"type": "tournament", "title": "Кубок", "tournament_id": tournament["id"]}
    ).json()
    announcement = admin.post(
        "/admin/promos",
        {"type": "fight_announcement", "title": "Анонс", "fighter1_id": first.id, "fighter2_id": second.id},
    ).json()
    fighter = admin.post(
        "/admin/promos",
        {
            "type": "fighter_of_week",
            "title": "Боец недели",
            "player_id": first.id,
            "show_from": now.isoformat(),
            "show_until": now.replace(year=2099).isoformat(),
        },
    ).json()
    assert first.get("/home").json()["promos"] == []

    for promo in (tournament_promo, announcement, fighter):
        assert admin.post(f"/admin/promos/{promo['id']}/publish", {"published": True}).status_code == 200
    assert [item["type"] for item in first.get("/home").json()["promos"]] == [
        "tournament",
        "fight_announcement",
        "fighter_of_week",
    ]

    admin.post(f"/admin/promos/{announcement['id']}/publish", {"published": False})
    assert len(first.get("/home").json()["promos"]) == 2

    expired_body = {
        "type": "fighter_of_week",
        "title": "Боец недели",
        "player_id": first.id,
        "show_from": now.replace(year=2020).isoformat(),
        "show_until": now.replace(year=2021).isoformat(),
    }
    assert admin.patch(f"/admin/promos/{fighter['id']}", expired_body).status_code == 200
    assert [item["type"] for item in first.get("/home").json()["promos"]] == ["tournament"]


def test_promo_validation(admin, players):
    first = players(1)[0]
    assert admin.post("/admin/promos", {"type": "tournament", "title": "T"}).status_code == 400
    assert (
        admin.post(
            "/admin/promos",
            {"type": "fight_announcement", "title": "A", "fighter1_id": first.id, "fighter2_id": first.id},
        ).status_code
        == 400
    )
    assert admin.post("/admin/promos", {"type": "fighter_of_week", "title": "F", "player_id": first.id}).status_code == 400


def test_home_lists_open_and_running_tournaments(admin, players):
    apis = players(2)
    draft = new_tournament(admin, publish=False)
    open_one = new_tournament(admin)
    running = new_tournament(admin)
    run_tournament_start(admin, running["id"], apis)
    ids = {item["id"] for item in apis[0].get("/home").json()["tournaments"]}
    assert ids == {open_one["id"], running["id"]}
    assert draft["id"] not in ids
