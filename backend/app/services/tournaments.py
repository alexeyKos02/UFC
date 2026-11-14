import random

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Belt,
    BeltKind,
    BeltWin,
    Fight,
    FightKind,
    FightStatus,
    Tournament,
    TournamentMatch,
    TournamentParticipant,
    TournamentStatus,
    User,
    UserStatus,
)
from app.schemas import FightResultIn, TournamentIn
from app.services import belts
from app.services.fight_records import create_fight_record
from app.services.rating import acquire_rating_lock

BELT_BUSY = "По этому поясу уже идёт турнир с открытой регистрацией или начавшимися боями"


def lock_tournament(db: Session, tournament_id: int) -> Tournament:
    tournament = db.scalar(
        select(Tournament)
        .where(Tournament.id == tournament_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if tournament is None:
        raise not_found("Турнир не найден")
    return tournament


def _check_belt(db: Session, belt_id: int) -> None:
    belt = db.get(Belt, belt_id)
    if belt is None:
        raise not_found("Пояс не найден")
    if belt.kind != BeltKind.TOURNAMENT:
        raise bad_request("Для турнира нужен турнирный пояс, основной разыгрывается в титульном бою")


def create_tournament(db: Session, actor: User, data: TournamentIn) -> Tournament:
    _check_belt(db, data.belt_id)
    tournament = Tournament(
        title=data.title,
        description=data.description,
        capacity=data.capacity,
        win_points=data.win_points,
        second_points=data.second_points,
        third_points=data.third_points,
        # Из двух участников полуфиналов нет, матч за 3-е место не нужен.
        has_third_place=data.has_third_place and data.capacity > 2,
        belt_id=data.belt_id,
        created_by_id=actor.id,
    )
    db.add(tournament)
    db.commit()
    return tournament


def seats_taken(db: Session, tournament_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TournamentParticipant)
        .where(TournamentParticipant.tournament_id == tournament_id)
    )


def update_tournament(db: Session, tournament_id: int, data: TournamentIn) -> Tournament:
    tournament = lock_tournament(db, tournament_id)
    tournament.title = data.title
    tournament.description = data.description
    changes_setup = data.capacity != tournament.capacity or data.belt_id != tournament.belt_id
    if changes_setup:
        if tournament.status not in (TournamentStatus.DRAFT, TournamentStatus.REGISTRATION):
            raise conflict("После старта нельзя менять лимит участников и пояс")
        if data.capacity < seats_taken(db, tournament_id):
            raise conflict("Лимит меньше числа уже записавшихся участников")
        _check_belt(db, data.belt_id)
        tournament.capacity = data.capacity
        tournament.belt_id = data.belt_id
    prizes = (data.win_points, data.second_points, data.third_points)
    if prizes != (tournament.win_points, tournament.second_points, tournament.third_points):
        if tournament.status in (TournamentStatus.FINISHED, TournamentStatus.CANCELLED):
            raise conflict("После завершения турнира нельзя менять призы")
        tournament.win_points, tournament.second_points, tournament.third_points = prizes
    wants_third = data.has_third_place and tournament.capacity > 2
    if wants_third != tournament.has_third_place:
        _set_third_place(db, tournament, wants_third)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict(BELT_BUSY) from None
    return tournament


def publish(db: Session, tournament_id: int) -> Tournament:
    tournament = lock_tournament(db, tournament_id)
    if tournament.status == TournamentStatus.REGISTRATION:
        return tournament
    if tournament.status != TournamentStatus.DRAFT:
        raise conflict("Открыть регистрацию можно только для черновика")
    tournament.status = TournamentStatus.REGISTRATION
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict(BELT_BUSY) from None
    return tournament


def join(db: Session, actor: User, tournament_id: int) -> Tournament:
    tournament = lock_tournament(db, tournament_id)
    if tournament.status != TournamentStatus.REGISTRATION:
        raise conflict("Регистрация на этот турнир закрыта")
    already = db.scalar(
        select(TournamentParticipant).where(
            TournamentParticipant.tournament_id == tournament_id, TournamentParticipant.user_id == actor.id
        )
    )
    if already is not None:
        return tournament
    if seats_taken(db, tournament_id) >= tournament.capacity:
        raise conflict("Свободных мест больше нет")
    db.add(TournamentParticipant(tournament_id=tournament_id, user_id=actor.id))
    db.commit()
    return tournament


def leave(db: Session, actor: User, tournament_id: int) -> Tournament:
    tournament = lock_tournament(db, tournament_id)
    if tournament.status != TournamentStatus.REGISTRATION:
        raise conflict("Отказаться от участия можно только до старта турнира")
    db.execute(
        delete(TournamentParticipant).where(
            TournamentParticipant.tournament_id == tournament_id, TournamentParticipant.user_id == actor.id
        )
    )
    db.commit()
    return tournament


def _generate_bracket(db: Session, tournament: Tournament, player_ids: list[int]) -> None:
    rng = random.SystemRandom()
    rng.shuffle(player_ids)

    bracket_size = 2
    while bracket_size < len(player_ids):
        bracket_size *= 2
    rounds_count = bracket_size.bit_length() - 1
    tournament.rounds_count = rounds_count

    matches: dict[tuple[int, int], TournamentMatch] = {}
    for round_no in range(1, rounds_count + 1):
        for position in range(bracket_size >> round_no):
            match = TournamentMatch(tournament_id=tournament.id, round=round_no, position=position)
            matches[(round_no, position)] = match
            db.add(match)

    if rounds_count < 2:
        tournament.has_third_place = False
    if tournament.has_third_place:
        db.add(_new_third_place_match(tournament))

    first_round_positions = list(range(bracket_size // 2))
    rng.shuffle(first_round_positions)
    byes_count = bracket_size - len(player_ids)
    players = iter(player_ids)
    for index, position in enumerate(first_round_positions):
        match = matches[(1, position)]
        match.player1_id = next(players)
        if index < byes_count:
            match.is_bye = True
            match.winner_id = match.player1_id
            _seat_in_next_round(matches[(2, position // 2)], position, match.player1_id)
        else:
            match.player2_id = next(players)
    db.flush()


def _seat_in_next_round(next_match: TournamentMatch, position: int, player_id: int) -> None:
    if position % 2 == 0:
        next_match.player1_id = player_id
    else:
        next_match.player2_id = player_id


def start(db: Session, tournament_id: int) -> Tournament:
    tournament = lock_tournament(db, tournament_id)
    if tournament.status == TournamentStatus.IN_PROGRESS:
        return tournament
    if tournament.status != TournamentStatus.REGISTRATION:
        raise conflict("Запустить можно только турнир с открытой регистрацией")
    player_ids = list(
        db.scalars(
            select(TournamentParticipant.user_id)
            .join(User, User.id == TournamentParticipant.user_id)
            .where(TournamentParticipant.tournament_id == tournament_id, User.status == UserStatus.ACTIVE)
        )
    )
    if len(player_ids) < 2:
        raise conflict("Для старта нужно минимум два активных участника")
    _generate_bracket(db, tournament, player_ids)
    _sync_third_place(db, tournament)
    tournament.status = TournamentStatus.IN_PROGRESS
    tournament.started_at = utcnow()
    db.commit()
    return tournament


def cancel(db: Session, tournament_id: int, reason: str) -> Tournament:
    acquire_rating_lock(db)
    tournament = lock_tournament(db, tournament_id)
    if tournament.status == TournamentStatus.CANCELLED:
        return tournament
    if tournament.status == TournamentStatus.FINISHED:
        raise conflict("Завершённый турнир нельзя отменить")
    tournament.status = TournamentStatus.CANCELLED
    tournament.cancel_reason = reason
    tournament.cancelled_at = utcnow()
    match_ids = select(TournamentMatch.id).where(TournamentMatch.tournament_id == tournament_id)
    db.execute(
        update(Fight)
        .where(
            Fight.tournament_match_id.in_(match_ids),
            Fight.status.in_([FightStatus.PENDING, FightStatus.DISPUTED]),
        )
        .values(status=FightStatus.CANCELLED)
    )
    db.commit()
    return tournament


def submit_match_result(db: Session, actor: User, match_id: int, data: FightResultIn) -> Fight:
    match = db.get(TournamentMatch, match_id)
    if match is None:
        raise not_found("Матч не найден")
    tournament = lock_tournament(db, match.tournament_id)
    db.refresh(match)
    if tournament.status != TournamentStatus.IN_PROGRESS:
        raise conflict("Турнир не идёт, результат внести нельзя")
    if actor.id not in (match.player1_id, match.player2_id):
        raise forbidden("Результат вносит один из участников матча")
    if match.is_bye or match.player1_id is None or match.player2_id is None:
        raise conflict("Пара для этого матча ещё не определена")
    if match.winner_id is not None:
        raise conflict("Результат матча уже подтверждён")
    existing = db.scalar(select(Fight).where(Fight.tournament_match_id == match_id))
    if existing is not None:
        if existing.initiator_id == actor.id:
            return existing
        raise conflict("Соперник уже внёс результат, откройте запись боя")
    fight = create_fight_record(
        db,
        FightKind.TOURNAMENT,
        actor,
        match.player1_id,
        match.player2_id,
        data,
        tournament_match_id=match.id,
    )
    db.commit()
    return fight


def on_fight_confirmed(db: Session, fight: Fight) -> None:
    """Вызывается внутри транзакции финального подтверждения.

    Финал отдаёт пояс; турнир завершается, когда сыграны финал и (если он есть) матч за 3-е место.
    Призы в очки лиги начисляет пересчёт очков сразу после этого вызова.
    """
    match = db.scalar(
        select(TournamentMatch)
        .where(TournamentMatch.id == fight.tournament_match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    tournament = lock_tournament(db, match.tournament_id)
    if tournament.status != TournamentStatus.IN_PROGRESS:
        raise conflict("Турнир не идёт, подтвердить результат нельзя")
    if match.winner_id is not None:
        raise conflict("Результат матча уже подтверждён")
    match.winner_id = fight.winner_id

    if match.is_third_place:
        pass
    elif match.round == tournament.rounds_count:
        tournament.winner_id = fight.winner_id
        belts.award(db, tournament.belt_id, fight, tournament_id=tournament.id)
    else:
        _seat_in_next_round(_next_match(db, tournament, match), match.position, fight.winner_id)
        if match.round == tournament.rounds_count - 1:
            db.flush()
            _sync_third_place(db, tournament)
    db.flush()
    _finish_if_done(db, tournament)
    db.flush()


def on_fight_deleted(db: Session, fight: Fight) -> None:
    """Откат подтверждённого боя турнира, который удаляет админ (внутри его транзакции).

    Матч снова ждёт результата. Победитель убирается из следующего круга, проигравший полуфиналист —
    из матча за 3-е место, если там ещё нет боя. Финал снова открывает турнир и забирает пояс,
    матч за 3-е место — только открывает. В отменённом турнире сетку не трогаем.
    """
    match = db.scalar(
        select(TournamentMatch)
        .where(TournamentMatch.id == fight.tournament_match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    tournament = lock_tournament(db, match.tournament_id)
    if tournament.status == TournamentStatus.CANCELLED or match.winner_id is None:
        return

    if match.is_third_place:
        pass
    elif match.round == tournament.rounds_count:
        win = db.scalar(select(BeltWin).where(BeltWin.tournament_id == tournament.id))
        if win is not None:
            belts.revoke(db, win)
        tournament.winner_id = None
    else:
        next_match = _next_match(db, tournament, match)
        if _has_fight(db, next_match) or next_match.winner_id is not None:
            raise conflict(
                "Победитель этого матча уже играл следующий круг. Сначала удалите или отмените бой следующего круга"
            )
        third = _third_place_match(db, tournament)
        semifinal = match.round == tournament.rounds_count - 1
        if semifinal and third is not None and (_has_fight(db, third) or (third.winner_id and not third.is_bye)):
            raise conflict("Матч за 3-е место уже сыгран или записан. Сначала удалите или отмените его бой")
        if match.position % 2 == 0:
            next_match.player1_id = None
        else:
            next_match.player2_id = None
    match.winner_id = None
    if tournament.status == TournamentStatus.FINISHED:
        tournament.status = TournamentStatus.IN_PROGRESS
        tournament.finished_at = None
    db.flush()
    if match.round == tournament.rounds_count - 1:
        _sync_third_place(db, tournament)
    db.flush()


def _lock_match(db: Session, stmt) -> TournamentMatch | None:
    return db.scalar(stmt.with_for_update().execution_options(populate_existing=True))


def _next_match(db: Session, tournament: Tournament, match: TournamentMatch) -> TournamentMatch:
    return _lock_match(
        db,
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament.id,
            TournamentMatch.round == match.round + 1,
            TournamentMatch.position == match.position // 2,
            TournamentMatch.is_third_place.is_(False),
        ),
    )


def _third_place_match(db: Session, tournament: Tournament) -> TournamentMatch | None:
    return _lock_match(
        db,
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament.id, TournamentMatch.is_third_place.is_(True)
        ),
    )


def _has_fight(db: Session, match: TournamentMatch) -> bool:
    return db.scalar(select(Fight.id).where(Fight.tournament_match_id == match.id)) is not None


def _new_third_place_match(tournament: Tournament) -> TournamentMatch:
    # Финал — позиция 0 последнего круга, матч за 3-е место стоит рядом с ним.
    return TournamentMatch(
        tournament_id=tournament.id, round=tournament.rounds_count, position=1, is_third_place=True
    )


def semifinal_losers(db: Session, tournament: Tournament) -> list[int | None]:
    """Проигравшие в полуфиналах по позициям 0 и 1; None — полуфинал не сыгран или без соперника."""
    if (tournament.rounds_count or 0) < 2:
        return []
    semis = {
        match.position: match
        for match in db.scalars(
            select(TournamentMatch).where(
                TournamentMatch.tournament_id == tournament.id,
                TournamentMatch.round == tournament.rounds_count - 1,
            )
        )
    }
    losers: list[int | None] = []
    for position in (0, 1):
        match = semis.get(position)
        if match is None or match.is_bye or match.winner_id is None:
            losers.append(None)
        else:
            losers.append(match.player2_id if match.winner_id == match.player1_id else match.player1_id)
    return losers


def _sync_third_place(db: Session, tournament: Tournament) -> None:
    """Сажает проигравших полуфиналистов в матч за 3-е место (пока его бой ещё не записан).

    Если полуфиналы сыграны, а проигравший только один (второй полуфинал без соперника),
    ему 3-е место достаётся без боя.
    """
    if not tournament.has_third_place:
        return
    third = _third_place_match(db, tournament)
    if third is None or _has_fight(db, third):
        return
    semis_done = db.scalar(
        select(func.count()).where(
            TournamentMatch.tournament_id == tournament.id,
            TournamentMatch.round == tournament.rounds_count - 1,
            TournamentMatch.winner_id.is_(None),
        )
    ) == 0
    losers = semifinal_losers(db, tournament)
    third.player1_id, third.player2_id = losers
    present = [loser for loser in losers if loser is not None]
    third.is_bye = semis_done and len(present) == 1
    third.winner_id = present[0] if third.is_bye else None
    db.flush()


def _finish_if_done(db: Session, tournament: Tournament) -> None:
    final = db.scalar(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament.id,
            TournamentMatch.round == tournament.rounds_count,
            TournamentMatch.is_third_place.is_(False),
        )
    )
    if final is None or final.winner_id is None:
        return
    third = _third_place_match(db, tournament) if tournament.has_third_place else None
    if third is not None and third.winner_id is None and not third.is_bye:
        return
    tournament.status = TournamentStatus.FINISHED
    tournament.finished_at = utcnow()


def _set_third_place(db: Session, tournament: Tournament, enabled: bool) -> None:
    """Галочка «Матч за 3-е место»: до старта — просто настройка, в идущем турнире — матч в сетке."""
    if tournament.status in (TournamentStatus.FINISHED, TournamentStatus.CANCELLED):
        raise conflict("После завершения турнира матч за 3-е место не включить и не убрать")
    if tournament.status != TournamentStatus.IN_PROGRESS:
        tournament.has_third_place = enabled
        return
    if enabled:
        if (tournament.rounds_count or 0) < 2:
            raise conflict("В сетке нет полуфиналов, матч за 3-е место не нужен")
        db.add(_new_third_place_match(tournament))
        tournament.has_third_place = True
        db.flush()
        _sync_third_place(db, tournament)
        return
    third = _third_place_match(db, tournament)
    if third is not None:
        if _has_fight(db, third):
            raise conflict("Бой за 3-е место уже записан. Сначала удалите или отмените его")
        db.delete(third)
    tournament.has_third_place = False
    db.flush()
    _finish_if_done(db, tournament)
