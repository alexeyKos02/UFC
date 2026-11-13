"""Пересчёт очков по дате боя: позднее подтверждение раннего боя, частичный пересчёт против полного."""

import random
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import RatingChange, User
from app.services import rating, recalc
from tests.conftest import FIGHT_TIME, confirm, create_fight, play


def at(hours: float):
    return FIGHT_TIME + timedelta(hours=hours)


def change_of(fight: dict, player) -> dict:
    return next(item for item in fight["rating_changes"] if item["player"]["id"] == player.id)


def test_late_confirmation_of_earlier_fight_recalculates_later_fights(players):
    a, b, c = players(3)
    early = create_fight(a, b, a, at(1)).json()
    later = play(a, c, a, at(2))
    assert change_of(later, a)["points_before"] == 1000

    confirm(b, early)
    early_detail = a.get(f"/fights/{early['id']}").json()
    later_detail = a.get(f"/fights/{later['id']}").json()
    # Ранний бой посчитан первым, поздний — уже от его итога.
    assert change_of(early_detail, a)["points_before"] == 1000
    assert change_of(later_detail, a)["points_before"] == change_of(early_detail, a)["points_after"]
    assert a.points() == change_of(later_detail, a)["points_after"]
    # Поздний бой помечен: его очки пересчитаны из-за раннего.
    assert later_detail["recalculated"]["because_fight_id"] == early["id"]
    assert early_detail["recalculated"] is None


def test_new_latest_fight_does_not_mark_others(players):
    a, b, c = players(3)
    first = play(a, b, a, at(1))
    play(a, c, c, at(2))
    assert a.get(f"/fights/{first['id']}").json()["recalculated"] is None


def test_rating_history_follows_fight_date(players):
    a, b, c = players(3)
    late = create_fight(a, c, a, at(2)).json()
    early = create_fight(a, b, b, at(1)).json()
    confirm(c, late)
    confirm(b, early)
    history = b.get(f"/players/{a.id}/rating-history").json()["points"]
    assert [item["fight_id"] for item in history] == [early["id"], late["id"]]
    assert history[1]["points_before"] == history[0]["points_after"]


def stored() -> tuple[dict, list]:
    with SessionLocal() as db:
        points = dict(db.execute(select(User.id, User.rating_points)).all())
        rows = db.execute(
            select(
                RatingChange.fight_id,
                RatingChange.player_id,
                RatingChange.place_before,
                RatingChange.points_before,
                RatingChange.delta,
                RatingChange.loss_discount,
                RatingChange.points_after,
                RatingChange.place_after,
                RatingChange.table_place_before,
                RatingChange.table_place_after,
                RatingChange.champion_before,
                RatingChange.champion_after,
            ).order_by(RatingChange.fight_id, RatingChange.player_id)
        ).all()
    return points, [tuple(row) for row in rows]


def test_partial_recalculation_matches_full_replay(admin, players):
    """Подтверждения в случайном порядке дают то же, что полный пересчёт истории с нуля."""
    apis = players(7)
    rnd = random.Random(7)
    created = []
    for index in range(30):
        first, second = rnd.sample(apis, 2)
        winner = rnd.choice([first, second])
        method = rnd.choice(["ko_tko", "submission", "decision", None])
        extra = {"method": method} if method else {}
        created.append((second, create_fight(first, second, winner, at(index * 3), **extra).json()))
    rnd.shuffle(created)
    for opponent, fight in created:
        assert confirm(opponent, fight).status_code == 200

    live = stored()
    with engine.begin() as connection:
        summary = recalc.recalculate(connection)
    assert summary["recalculated_fights"] == []
    assert stored() == live


def test_tie_break_with_counters_matches_full_scan():
    """Счётчики личных встреч разбирают равных так же, как перебор всех боёв в rating.break_tie."""
    rnd = random.Random(3)
    for _ in range(200):
        ids = list(range(1, rnd.randint(3, 8)))
        fights = [
            (*rnd.sample(ids, 2), rnd.choice(["ko_tko", "submission", "decision", None]))
            for _ in range(rnd.randint(0, 12))
        ]
        h2h = recalc.HeadToHead()
        for winner, loser, method in fights:
            h2h.add(winner, loser, method)
        names = {player: rnd.choice(["Борис", "Ёжик", "Анна", "Ева", "Жора"]) + str(player) for player in ids}
        users = [SimpleNamespace(id=player, nickname=names[player]) for player in ids]
        expected = [user.id for user in rating.break_tie(users, fights)]
        actual = recalc.break_tie(ids, h2h, lambda player: names[player].casefold().replace("ё", "е"))
        assert actual == expected
