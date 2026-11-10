from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import not_found
from app.models import Belt, BeltKind, BeltWin, Fight


def main_belt(db: Session, lock: bool = False) -> Belt:
    stmt = select(Belt).where(Belt.kind == BeltKind.MAIN)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    belt = db.scalar(stmt)
    if belt is None:
        raise not_found("Основной пояс не настроен")
    return belt


def award(
    db: Session,
    belt_id: int,
    fight: Fight,
    tournament_id: int | None = None,
    title_fight_id: int | None = None,
) -> BeltWin:
    belt = db.scalar(
        select(Belt).where(Belt.id == belt_id).with_for_update().execution_options(populate_existing=True)
    )
    previous = belt.current_champion_id
    win = BeltWin(
        belt_id=belt.id,
        user_id=fight.winner_id,
        fight_id=fight.id,
        tournament_id=tournament_id,
        title_fight_id=title_fight_id,
        previous_champion_id=previous,
        is_defense=previous == fight.winner_id,
        won_at=fight.fought_at,
    )
    belt.current_champion_id = fight.winner_id
    db.add(win)
    db.flush()
    return win
