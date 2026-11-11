from datetime import timedelta

from tests.conftest import FIGHT_TIME, confirm, create_fight, play
from tests.test_adjustments_and_special_places import body, upset_setup


def h2h(viewer, other) -> dict:
    return viewer.get(f"/players/{other.id}").json()["head_to_head"]


def fight(initiator, opponent, winner, hours: int, **extra) -> None:
    created = create_fight(initiator, opponent, winner, FIGHT_TIME + timedelta(hours=hours), **extra)
    assert created.status_code == 201, created.text
    assert confirm(opponent, created.json()).status_code == 200


def test_head_to_head_from_both_sides(players):
    me, rival = players(2)
    fight(me, rival, me, 1, method="ko_tko", round=1)
    fight(rival, me, rival, 2, method="decision")
    fight(me, rival, me, 3, method="ko_tko", round=2)
    fight(me, rival, me, 4)

    mine = h2h(me, rival)
    assert (mine["fights"], mine["my_wins"], mine["their_wins"]) == (4, 3, 1)
    assert mine["methods"] == {"mine": {"ko_tko": 2, "none": 1}, "theirs": {"decision": 1}}
    assert mine["streak"] == {"mine": True, "count": 2}
    # Других боёв нет, поэтому весь прирост очков — из этих встреч.
    assert mine["points"] == me.points() - 1000
    assert [item["won"] for item in mine["recent"]] == [True, True, False, True]
    assert mine["recent"][1]["method"] == "ko_tko" and mine["recent"][1]["round"] == 2

    theirs = h2h(rival, me)
    assert (theirs["my_wins"], theirs["their_wins"]) == (1, 3)
    assert theirs["streak"] == {"mine": False, "count": 2}
    assert theirs["points"] == -mine["points"]


def test_no_head_to_head_on_own_profile_and_before_first_fight(players):
    me, rival = players(2)
    assert me.get(f"/players/{me.id}").json()["head_to_head"] is None
    empty = h2h(me, rival)
    assert (empty["fights"], empty["streak"], empty["recent"], empty["points"]) == (0, None, [], 0)


def test_unconfirmed_and_other_fights_are_not_counted(players):
    me, rival, other = players(3)
    create_fight(me, rival, me)
    play(me, other, me)
    assert h2h(me, rival)["fights"] == 0


def test_recent_shows_last_five(players):
    me, rival = players(2)
    for hour in range(7):
        fight(me, rival, me, hour)
    result = h2h(me, rival)
    assert result["fights"] == 7
    assert len(result["recent"]) == 5
    assert result["streak"] == {"mine": True, "count": 7}


def test_points_include_manual_adjustment(admin, players):
    top, bottom, upset, _ = upset_setup(players)
    before = h2h(bottom, top)["points"]
    assert admin.put(f"/admin/rating/adjustments/{upset['id']}", body(bottom, 20)).status_code == 200
    assert h2h(bottom, top)["points"] == before + 20
    assert h2h(top, bottom)["points"] == -(before + 20)
