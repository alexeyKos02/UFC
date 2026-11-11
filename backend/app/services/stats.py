from collections import Counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AdjustmentStatus, Fight, FightStatus, RatingAdjustment, RatingChange, User


def _win_rate(wins: int, total: int) -> float | None:
    return round(wins * 100 / total, 1) if total else None


def league_stats(db: Session) -> dict[int, dict]:
    confirmed = Fight.status == FightStatus.CONFIRMED
    wins = dict(db.execute(select(Fight.winner_id, func.count()).where(confirmed).group_by(Fight.winner_id)).all())
    losses = dict(db.execute(select(Fight.loser_id, func.count()).where(confirmed).group_by(Fight.loser_id)).all())
    result: dict[int, dict] = {}
    for user_id in wins.keys() | losses.keys():
        user_wins, user_losses = wins.get(user_id, 0), losses.get(user_id, 0)
        total = user_wins + user_losses
        result[user_id] = {
            "fights": total,
            "wins": user_wins,
            "losses": user_losses,
            "win_rate": _win_rate(user_wins, total),
        }
    return result


EMPTY_STATS = {"fights": 0, "wins": 0, "losses": 0, "win_rate": None}


def fight_comparison(db: Session, fight: Fight) -> dict:
    """Сравнение участников для раскрытой карточки: значения идут в порядке player1, player2."""
    league = league_stats(db)
    first = league.get(fight.player1_id, EMPTY_STATS)
    second = league.get(fight.player2_id, EMPTY_STATS)
    pair = (fight.player1_id, fight.player2_id)
    head_to_head = dict(
        db.execute(
            select(Fight.winner_id, func.count())
            .where(Fight.status == FightStatus.CONFIRMED, Fight.winner_id.in_(pair), Fight.loser_id.in_(pair))
            .group_by(Fight.winner_id)
        ).all()
    )
    return {
        "head_to_head": [head_to_head.get(fight.player1_id, 0), head_to_head.get(fight.player2_id, 0)],
        "league_wins": [first["wins"], second["wins"]],
        "league_losses": [first["losses"], second["losses"]],
    }


def confirmed_fights_of(db: Session, user_id: int) -> list[Fight]:
    return list(
        db.scalars(
            select(Fight)
            .where(Fight.status == FightStatus.CONFIRMED, or_(Fight.winner_id == user_id, Fight.loser_id == user_id))
            .order_by(Fight.fought_at, Fight.id)
        )
    )


def _leaders(db: Session, counter: Counter) -> list[tuple[User, int]]:
    if not counter:
        return []
    top = max(counter.values())
    ids = [user_id for user_id, count in counter.items() if count == top]
    players = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.nickname)).all()
    return [(player, top) for player in players]


def player_stats(db: Session, user_id: int) -> dict:
    fights = confirmed_fights_of(db, user_id)
    wins = losses = streak = best_streak = 0
    beaten: Counter = Counter()
    lost_to: Counter = Counter()
    for fight in fights:
        if fight.winner_id == user_id:
            wins += 1
            streak += 1
            best_streak = max(best_streak, streak)
            beaten[fight.loser_id] += 1
        else:
            losses += 1
            streak = 0
            lost_to[fight.winner_id] += 1
    return {
        "fights": wins + losses,
        "wins": wins,
        "losses": losses,
        "win_rate": _win_rate(wins, wins + losses),
        "best_streak": best_streak,
        "nemeses": _leaders(db, lost_to),
        "victims": _leaders(db, beaten),
    }


RECENT_HEAD_TO_HEAD = 5


def head_to_head(db: Session, me_id: int, rival_id: int) -> dict:
    """Очные встречи зрителя (me) с игроком на странице профиля (rival): всё с точки зрения зрителя."""
    pair = (me_id, rival_id)
    fights = list(
        db.scalars(
            select(Fight)
            .where(Fight.status == FightStatus.CONFIRMED, Fight.winner_id.in_(pair), Fight.loser_id.in_(pair))
            .order_by(Fight.fought_at, Fight.id)
        )
    )
    methods = {side: Counter() for side in ("mine", "theirs")}
    my_wins = 0
    streak_owner: int | None = None
    streak = 0
    for fight in fights:
        mine = fight.winner_id == me_id
        my_wins += mine
        methods["mine" if mine else "theirs"][fight.method.value if fight.method else "none"] += 1
        streak = streak + 1 if streak_owner == fight.winner_id else 1
        streak_owner = fight.winner_id

    # Сколько очков рейтинга зритель выиграл (или отдал) в этих боях: автоначисления плюс ручные корректировки.
    fight_ids = [fight.id for fight in fights]
    points = 0
    if fight_ids:
        points += db.scalar(
            select(func.coalesce(func.sum(RatingChange.delta), 0)).where(
                RatingChange.fight_id.in_(fight_ids), RatingChange.player_id == me_id
            )
        )
        for fight_id, winner_delta in db.execute(
            select(RatingAdjustment.fight_id, RatingAdjustment.winner_delta).where(
                RatingAdjustment.fight_id.in_(fight_ids), RatingAdjustment.status == AdjustmentStatus.ACTIVE
            )
        ):
            winner_id = next(fight.winner_id for fight in fights if fight.id == fight_id)
            points += winner_delta if winner_id == me_id else -winner_delta

    return {
        "fights": len(fights),
        "my_wins": my_wins,
        "their_wins": len(fights) - my_wins,
        "methods": {side: dict(counter) for side, counter in methods.items()},
        "streak": {"mine": streak_owner == me_id, "count": streak} if fights else None,
        "points": points,
        "recent": [
            {
                "fight_id": fight.id,
                "fought_at": fight.fought_at,
                "won": fight.winner_id == me_id,
                "method": fight.method.value if fight.method else None,
                "round": fight.round_no,
                "kind": fight.kind.value,
            }
            for fight in reversed(fights[-RECENT_HEAD_TO_HEAD:])
        ],
    }
