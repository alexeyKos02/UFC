from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.rating import auto_delta, break_tie
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


def display_order(api) -> list[int]:
    return [row["player"]["id"] for row in api.get("/players").json()]


def test_equal_points_get_own_numbers_but_share_points_place(admin, players):
    first, second, third, fourth = players(4)
    play(first, second, first)
    # Очки: first 102, admin, third и fourth по 100, second 98.
    table = table_of(admin)
    order = (first, admin, third, fourth, second)
    assert [table[api.id]["display_place"] for api in order] == [1, 2, 3, 4, 5]
    assert [table[api.id]["points_place"] for api in order] == [1, 2, 2, 2, 3]


def test_head_to_head_beats_alphabet_at_equal_points(players):
    first, second, third = players(3)
    play(second, first, second)
    play(first, third, first)
    play(first, third, first)
    assert first.points() == second.points()
    assert display_order(first) == [second.id, first.id, third.id]


@pytest.mark.parametrize(
    ("better", "worse"),
    [("ko_tko", "submission"), ("submission", "decision"), ("decision", None)],
)
def test_stronger_win_method_ranks_higher_when_head_to_head_is_even(players, better, worse):
    first, second = players(2)
    confirm(first, create_fight(second, first, second, method=better).json())
    confirm(second, create_fight(first, second, first, method=worse).json())
    assert first.points() == second.points()
    assert display_order(first) == [second.id, first.id]


def test_alphabet_is_the_last_tiebreak(players):
    first, second, third = players(3)
    for api, nickname in ((first, "Яна"), (second, "Борис"), (third, "Ёжик")):
        assert api.patch("/me/profile", {"nickname": nickname}).status_code == 200
    assert display_order(first) == [second.id, third.id, first.id]


def test_three_way_cycle_is_decided_by_win_methods(players):
    first, second, third = players(3)
    confirm(second, create_fight(first, second, first, method="decision").json())
    confirm(third, create_fight(second, third, second, method="ko_tko").json())
    confirm(first, create_fight(third, first, third, method="submission").json())
    assert len({api.points() for api in (first, second, third)}) == 1
    assert display_order(first) == [second.id, third.id, first.id]


def test_tie_is_recounted_inside_remaining_group():
    leader = SimpleNamespace(id=1, nickname="Я")
    middle_winner = SimpleNamespace(id=2, nickname="Б")
    middle_loser = SimpleNamespace(id=3, nickname="А")
    last = SimpleNamespace(id=4, nickname="В")
    fights = [
        (leader.id, middle_winner.id, None),
        (middle_winner.id, middle_loser.id, None),
        (middle_loser.id, last.id, None),
    ]
    players = [middle_loser, last, middle_winner, leader]
    assert break_tie(players, fights) == [leader, middle_winner, middle_loser, last]


def test_fights_with_players_outside_the_tie_are_ignored():
    first = SimpleNamespace(id=1, nickname="Б")
    second = SimpleNamespace(id=2, nickname="А")
    outsider_id = 3
    assert break_tie([first, second], [(first.id, outsider_id, None)]) == [second, first]


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
