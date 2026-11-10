from tests.test_rating_champion import crown


def tier_of(viewer, player_id: int) -> str | None:
    return viewer.get(f"/players/{player_id}").json()["rating"]["tier"]


def test_tier_boundaries_follow_table_numbers(admin, players):
    apis = players(21)
    rows = admin.get("/players").json()
    by_place = {row["display_place"]: row["player"]["id"] for row in rows}
    assert len(by_place) == 22

    expected = {1: "top", 5: "top", 6: "middle", 20: "middle", 21: "bottom", 22: "bottom"}
    assert {place: tier_of(apis[0], by_place[place]) for place in expected} == expected


def test_champion_without_table_number_is_top(admin, players):
    champion, challenger, strong, weak = players(4)
    crown(admin, champion, challenger)
    assert tier_of(weak, champion.id) == "top"


def test_special_place_counts_for_the_tier(admin, players):
    apis = players(9)
    rows = admin.get("/players").json()
    last = rows[-1]
    assert last["display_place"] == 10
    assert tier_of(apis[0], last["player"]["id"]) == "middle"

    assert admin.put(f"/admin/rating/special-places/{last['player']['id']}", {"place": 2}).status_code == 200
    assert tier_of(apis[0], last["player"]["id"]) == "top"


def test_blocked_player_has_no_tier(owner, players):
    first, second = players(2)
    owner.post(f"/admin/users/{first.id}/block")
    assert tier_of(second, first.id) is None
