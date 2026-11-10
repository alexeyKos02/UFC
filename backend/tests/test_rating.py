from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.services.rating import auto_delta
from tests.conftest import FIGHT_TIME, confirm, create_fight, ladder, play


@pytest.mark.parametrize(
    ("winner_place", "loser_place", "expected"),
    [
        (7, 3, 5),
        (6, 3, 5),
        (5, 3, 2),
        (4, 3, 2),
        (3, 3, 2),
        (3, 5, 2),
        (3, 7, 2),
    ],
)
def test_delta_table(winner_place, loser_place, expected):
    assert auto_delta(winner_place, loser_place) == expected


def table_of(api) -> dict[int, dict]:
    return {row["player"]["id"]: row for row in api.get("/players").json()}


def test_equal_points_share_place_without_gaps(players):
    first, second, third, fourth = players(4)
    play(first, second, first)
    table = table_of(first)
    assert table[first.id]["display_place"] == 1
    assert table[third.id]["display_place"] == 2
    assert table[fourth.id]["display_place"] == 2
    assert table[second.id]["display_place"] == 3


def test_upset_when_lower_by_three_places(players):
    apis = players(4)
    ladder(apis)
    top, _, _, bottom = apis
    places = table_of(top)
    assert places[bottom.id]["display_place"] - places[top.id]["display_place"] == 3

    top_before, bottom_before = top.points(), bottom.points()
    fight = play(bottom, top, bottom)
    assert bottom.points() == bottom_before + 5
    assert top.points() == top_before - 5
    assert bottom.points() + top.points() == top_before + bottom_before

    changes = {item["player"]["id"]: item for item in fight["rating_changes"]}
    assert changes[bottom.id]["place_before"] == 4
    assert changes[bottom.id]["points_before"] == bottom_before
    assert changes[bottom.id]["delta"] == 5
    assert changes[bottom.id]["points_after"] == bottom_before + 5
    assert changes[top.id]["place_before"] == 1
    assert changes[top.id]["delta"] == -5


def test_two_place_gap_is_regular(players):
    apis = players(3)
    ladder(apis)
    top, _, bottom = apis
    bottom_before = bottom.points()
    play(bottom, top, bottom)
    assert bottom.points() == bottom_before + 2


def test_favorite_wins_regular_points(players):
    apis = players(4)
    ladder(apis)
    top, _, _, bottom = apis
    top_before = top.points()
    play(top, bottom, top)
    assert top.points() == top_before + 2


def test_points_can_go_negative(players):
    weak, strong = players(2)
    for hour in range(55):
        play(strong, weak, strong, FIGHT_TIME + timedelta(hours=hour))
    assert weak.points() < 0
    assert weak.points() + strong.points() == 200


def test_new_registration_shares_starting_points(players):
    apis = players(2)
    play(apis[0], apis[1], apis[0])
    from tests.conftest import register

    late = register("latecomer")
    assert late.points() == 100
    assert table_of(late)[late.id]["display_place"] == 2


def test_parallel_final_confirmations_use_sequential_state(players):
    """Каждый расчёт видит очки после предыдущего: цепочка снимков points_before не рвётся."""
    apis = players(8)
    hub, *others = apis
    fights = [create_fight(hub, other, hub).json() for other in others]
    with ThreadPoolExecutor(len(others)) as pool:
        responses = list(pool.map(lambda pair: confirm(pair[0], pair[1]), zip(others, fights, strict=True)))
    assert {response.status_code for response in responses} == {200}

    snapshots = []
    for fight in fights:
        detail = hub.get(f"/fights/{fight['id']}").json()
        snapshots.append(next(item for item in detail["rating_changes"] if item["player"]["id"] == hub.id))
    snapshots.sort(key=lambda item: item["points_before"])
    assert snapshots[0]["points_before"] == 100
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        assert current["points_before"] == previous["points_after"]
    assert hub.points() == 100 + 2 * len(others)
    total = sum(api.points() for api in apis)
    assert total == 100 * len(apis)


def test_database_rejects_second_rating_change_for_same_fight(players):
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models import RatingChange

    first, second = players(2)
    fight = play(first, second, first)
    db = SessionLocal()
    db.add(
        RatingChange(
            fight_id=fight["id"], player_id=first.id, place_before=1, points_before=1, delta=2, points_after=3
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()
