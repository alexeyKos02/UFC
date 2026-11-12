from tests.conftest import expected_gain
from tests.conftest import ladder, play
from tests.test_belts import play_title, schedule


def table(api) -> list[dict]:
    return api.get("/players").json()


def crown(admin, champion, challenger) -> None:
    play_title(schedule(admin, challenger, champion).json(), champion, challenger, champion)


def test_champion_is_first_without_number_and_others_start_from_one(admin, players):
    champion, challenger, third = players(3)
    crown(admin, champion, challenger)
    # Очки: чемпион 1020, админ и third по 1000, challenger 980.
    rows = table(third)
    assert rows[0]["player"]["id"] == champion.id
    assert rows[0]["is_champion"] is True
    assert rows[0]["display_place"] is None
    assert {row["player"]["id"]: row["display_place"] for row in rows[1:]} == {
        admin.id: 1,
        third.id: 2,
        challenger.id: 3,
    }
    assert not any(row["is_champion"] for row in rows[1:])
    assert rows[0]["belt"]["kind"] == "main"
    assert "full_body_url" in rows[0]["player"]
    assert all("belt" not in row and "full_body_url" not in row["player"] for row in rows[1:])


def test_champion_stays_on_top_with_fewer_points(admin, players):
    champion, challenger, strong, weak = players(4)
    crown(admin, champion, challenger)
    for _ in range(3):
        play(strong, weak, strong)
    rows = table(admin)
    assert rows[0]["player"]["id"] == champion.id
    assert rows[0]["points_place"] == 2
    assert rows[1]["player"]["id"] == strong.id
    assert rows[1]["display_place"] == 1


def test_vacant_belt_has_no_champion_row(players):
    first, second = players(2)
    rows = table(first)
    assert not any(row["is_champion"] for row in rows)
    assert sorted(row["display_place"] for row in rows) == [1, 2]


def test_profile_shows_champion_instead_of_number(admin, players):
    champion, challenger = players(2)
    crown(admin, champion, challenger)
    rating = champion.profile()["rating"]
    assert rating["is_champion"] is True
    assert rating["display_place"] is None
    assert admin.get(f"/players/{champion.id}").json()["rating"]["points_place"] == 1
    other = challenger.profile()["rating"]
    assert other["is_champion"] is False
    assert other["display_place"] == 2


def test_champion_display_does_not_change_points_or_upsets(admin, players):
    top, champion, bottom = players(3)
    ladder([top, champion, admin, bottom])
    crown(admin, champion, bottom)

    rows = {row["player"]["id"]: row for row in table(admin)}
    assert rows[top.id]["display_place"] == 1
    assert rows[admin.id]["display_place"] == 2
    assert rows[bottom.id]["display_place"] == 3
    assert rows[bottom.id]["points_place"] == 4

    bottom_before, top_before = bottom.points(), top.points()
    fight = play(bottom, top, bottom)
    assert bottom.points() == bottom_before + expected_gain(bottom_before, top_before)
    changes = {item["player"]["id"]: item for item in fight["rating_changes"]}
    assert changes[bottom.id]["place_before"] == 4
    assert changes[top.id]["place_before"] == 1


def test_special_place_keeps_its_number_under_champion(admin, players):
    champion, challenger, pinned = players(3)
    crown(admin, champion, challenger)
    assert admin.put(f"/admin/rating/special-places/{pinned.id}", {"place": 1}).status_code == 200
    rows = table(admin)
    assert [(row["player"]["id"], row["display_place"]) for row in rows[:2]] == [
        (champion.id, None),
        (pinned.id, 1),
    ]
    assert rows[1]["is_special"] is True


def test_champion_pin_applies_only_after_belt_is_lost(admin, players):
    champion, challenger = players(2)
    crown(admin, champion, challenger)
    assert admin.put(f"/admin/rating/special-places/{champion.id}", {"place": 1}).status_code == 200

    rows = table(admin)
    assert rows[0]["player"]["id"] == champion.id
    assert rows[0]["is_special"] is False
    assert [row["display_place"] for row in rows[1:]] == [1, 2]

    play_title(schedule(admin, challenger).json(), challenger, champion, challenger)
    rows = table(admin)
    assert rows[0]["player"]["id"] == challenger.id
    former = next(row for row in rows if row["player"]["id"] == champion.id)
    assert former["display_place"] == 1
    assert former["is_special"] is True


def test_blocked_champion_is_hidden_and_numbering_starts_from_one(owner, admin, players):
    champion, challenger = players(2)
    crown(admin, champion, challenger)
    owner.post(f"/admin/users/{champion.id}/block")
    rows = table(admin)
    assert champion.id not in [row["player"]["id"] for row in rows]
    assert not any(row["is_champion"] for row in rows)
    assert min(row["display_place"] for row in rows) == 1
