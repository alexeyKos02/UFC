from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import conflict, not_found
from app.models import Belt, BeltKind, BeltWin, Fight, TitleFight, TitleFightStatus, User, UserStatus
from app.services.rating import acquire_rating_lock


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


def award_manually(db: Session, actor: User, belt_id: int, player_id: int) -> Belt:
    """Админ или владелец отдаёт пояс игроку без боя. Прошлый чемпион, если был, его теряет."""
    # Чемпион основного пояса стоит над таблицей рейтинга, поэтому замок рейтинга идёт первым.
    acquire_rating_lock(db)
    belt = db.scalar(
        select(Belt).where(Belt.id == belt_id).with_for_update().execution_options(populate_existing=True)
    )
    if belt is None:
        raise not_found("Пояс не найден")
    player = db.get(User, player_id)
    if player is None:
        raise not_found("Игрок не найден")
    if player.status != UserStatus.ACTIVE:
        raise conflict(f"Игрок {player.nickname} заблокирован, выдать пояс нельзя")
    if belt.current_champion_id == player.id:
        raise conflict(f"Пояс уже у игрока {player.nickname}")
    if belt.kind == BeltKind.MAIN and db.scalar(
        select(TitleFight.id).where(TitleFight.status == TitleFightStatus.SCHEDULED)
    ):
        raise conflict("Назначен бой за основной пояс. Сначала завершите или отмените его")

    db.add(
        BeltWin(
            belt_id=belt.id,
            user_id=player.id,
            awarded_by_id=actor.id,
            previous_champion_id=belt.current_champion_id,
            is_defense=False,
            won_at=utcnow(),
        )
    )
    belt.current_champion_id = player.id
    db.commit()
    return belt


def revoke(db: Session, win: BeltWin) -> None:
    """Откатывает переход пояса (бой с этим результатом удалён): пояс возвращается прежнему чемпиону.

    Только если это последний переход пояса: иначе после него пояс уже кто-то брал или защищал.
    """
    belt = db.scalar(
        select(Belt).where(Belt.id == win.belt_id).with_for_update().execution_options(populate_existing=True)
    )
    later = db.scalar(select(BeltWin.id).where(BeltWin.belt_id == belt.id, BeltWin.id > win.id).limit(1))
    if later is not None:
        raise conflict(
            f"После этого боя пояс «{belt.name}» уже переходил или защищался. "
            "Сначала удалите более поздние бои за этот пояс"
        )
    belt.current_champion_id = win.previous_champion_id
    db.delete(win)
    db.flush()
