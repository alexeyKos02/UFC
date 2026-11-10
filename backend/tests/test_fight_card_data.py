from tests.conftest import create_fight, play
from tests.test_adjustments_and_special_places import body, upset_setup


def brief_of(api, fight_id: int) -> dict:
    return next(item for item in api.get("/fights").json()["items"] if item["id"] == fight_id)


def test_list_item_has_photo_fields_and_points_by_side(players):
    first, second = players(2)
    fight = play(first, second, first)
    brief = brief_of(first, fight["id"])
    assert brief["points_change"] == [2, -2]
    assert brief["player1"]["full_body_url"] is None
    assert "full_body_url" in brief["player2"]


def test_points_by_side_follow_player_order_when_second_player_wins(players):
    first, second = players(2)
    fight = play(first, second, second)
    assert brief_of(first, fight["id"])["points_change"] == [-2, 2]


def test_points_by_side_include_manual_adjustment(admin, players):
    top, bottom, fight, _ = upset_setup(players)
    assert admin.put(f"/admin/rating/adjustments/{fight['id']}", body(bottom, 2)).status_code == 200
    assert brief_of(admin, fight["id"])["points_change"] == [7, -7]


def test_unconfirmed_fight_has_no_points_yet(players):
    first, second = players(2)
    create_fight(first, second, first)
    assert second.get("/fights/mine").json()["to_confirm"][0]["points_change"] is None


def test_detail_compares_both_players(players):
    first, second, third = players(3)
    play(first, second, first)
    play(second, first, second)
    fight = play(first, second, first)
    play(first, third, first)
    assert first.get(f"/fights/{fight['id']}").json()["comparison"] == {
        "head_to_head": [2, 1],
        "league_wins": [3, 1],
        "league_losses": [1, 2],
    }
