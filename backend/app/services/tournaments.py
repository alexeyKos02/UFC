import random

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Belt,
    BeltKind,
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
    if data.win_points != tournament.win_points:
        if tournament.status in (TournamentStatus.FINISHED, TournamentStatus.CANCELLED):
            raise conflict("После завершения турнира нельзя менять очки за победу")
        tournament.win_points = data.win_points
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
    """Вызывается внутри транзакции финального подтверждения."""
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

    if match.round == tournament.rounds_count:
        tournament.status = TournamentStatus.FINISHED
        tournament.winner_id = fight.winner_id
        tournament.finished_at = utcnow()
        belts.award(db, tournament.belt_id, fight, tournament_id=tournament.id)
        # Вызов идёт под замком рейтинга, который взяло финальное подтверждение.
        db.execute(
            update(User)
            .where(User.id == fight.winner_id)
            .values(rating_points=User.rating_points + tournament.win_points)
        )
    else:
        next_match = db.scalar(
            select(TournamentMatch)
            .where(
                TournamentMatch.tournament_id == tournament.id,
                TournamentMatch.round == match.round + 1,
                TournamentMatch.position == match.position // 2,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        _seat_in_next_round(next_match, match.position, fight.winner_id)
    db.flush()
