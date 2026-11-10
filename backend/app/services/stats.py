from collections import Counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Fight, FightStatus, User


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
