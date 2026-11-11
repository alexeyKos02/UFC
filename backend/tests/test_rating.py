from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.rating import break_tie, elo_delta, expected_score
from tests.conftest import FIGHT_TIME, confirm, create_fight, ladder, play, set_points


@pytest.mark.parametrize(
    ("winner_points", "loser_points", "expected"),
    [
        (1000, 1000, 20),
        (1000, 1100, 26),
        (900, 1100, 30),
        (600, 1000, 36),
        (1100, 1000, 14),
        (1100, 900, 10),
        (1000, 600, 4),
        (2500, 500, 1),
    ],
)
def test_elo_delta_table(winner_points, loser_points, expected):
    assert elo_delta(winner_points, loser_points) == expected


def test_expected_scores_sum_to_one():
    assert expected_score(1000, 1000) == 0.5
    assert expected_score(1240, 1000) + expected_score(1000, 1240) == pytest.approx(1)


def table_of(api) -> dict[int, dict]:
    return {row["player"]["id"]: row for row in api.get("/players").json()}


def display_order(api) -> list[int]:
    return [row["player"]["id"] for row in api.get("/players").json()]


def test_equal_points_get_own_numbers_but_share_points_place(admin, players):
    first, second, third, fourth = players(4)
    play(first, second, first)
    # Очки: first 1020, admin, third и fourth по 1000, second 980.
    table = table_of(admin)
    order = (first, admin, third, fourth, second)
    assert [table[api.id]["display_place"] for api in order] == [1, 2, 3, 4, 5]
    assert [table[api.id]["points_place"] for api in order] == [1, 2, 2, 2, 3]


def test_head_to_head_beats_alphabet_at_equal_points(players):
    first, second, third = players(3)
    play(second, first, second)
    play(first, third, first)
    play(first, third, first)
    set_points([first, second])
    assert display_order(first) == [second.id, first.id, third.id]


@pytest.mark.parametrize(
    ("better", "worse"),
    [("ko_tko", "submission"), ("submission", "decision"), ("decision", None)],
)
def test_stronger_win_method_ranks_higher_when_head_to_head_is_even(players, better, worse):
    first, second = players(2)
    confirm(first, create_fight(second, first, second, method=better).json())
    confirm(second, create_fight(first, second, first, method=worse).json())
    set_points([first, second])
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
    set_points([first, second, third])
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


def test_underdog_win_uses_elo_and_keeps_total(players):
    apis = players(4)
    ladder(apis)
    top, _, _, bottom = apis
    places = table_of(top)
    assert places[bottom.id]["display_place"] - places[top.id]["display_place"] == 3

    top_before, bottom_before = top.points(), bottom.points()
    fight = play(bottom, top, bottom)
    gain = elo_delta(bottom_before, top_before)
    assert gain > 20
    assert bottom.points() == bottom_before + gain
    assert top.points() == top_before - gain
    assert bottom.points() + top.points() == top_before + bottom_before

    changes = {item["player"]["id"]: item for item in fight["rating_changes"]}
    assert changes[bottom.id]["place_before"] == 4
    assert changes[bottom.id]["points_before"] == bottom_before
    assert changes[bottom.id]["delta"] == gain
    assert changes[bottom.id]["points_after"] == bottom_before + gain
    assert changes[top.id]["place_before"] == 1
    assert changes[top.id]["delta"] == -gain


def test_favorite_win_gives_less_than_even_fight(players):
    apis = players(4)
    ladder(apis)
    top, _, _, bottom = apis
    top_before, bottom_before = top.points(), bottom.points()
    play(top, bottom, top)
    gain = top.points() - top_before
    assert gain == elo_delta(top_before, bottom_before)
    assert 1 <= gain < 20


def test_beating_the_same_weak_player_brings_less_and_less(players):
    weak, strong = players(2)
    gains = []
    for hour in range(10):
        before = strong.points()
        play(strong, weak, strong, FIGHT_TIME + timedelta(hours=hour))
        gains.append(strong.points() - before)
    assert gains == sorted(gains, reverse=True)
    assert gains[0] == 20
    assert gains[-1] < 10
    assert weak.points() + strong.points() == 2000


def test_new_registration_shares_starting_points(players):
    apis = players(2)
    play(apis[0], apis[1], apis[0])
    from tests.conftest import register

    late = register("latecomer")
    assert late.points() == 1000
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
    assert snapshots[0]["points_before"] == 1000
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        assert current["points_before"] == previous["points_after"]
    assert hub.points() == snapshots[-1]["points_after"]
    total = sum(api.points() for api in apis)
    assert total == 1000 * len(apis)


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
