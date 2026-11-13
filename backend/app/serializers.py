"""Преобразование моделей в ответы API."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AdjustmentStatus,
    Belt,
    BeltKind,
    BeltWin,
    Fight,
    FightStatus,
    Promo,
    RatingAdjustment,
    SpecialPlace,
    TitleFight,
    TitleFightStatus,
    Tournament,
    TournamentMatch,
    TournamentParticipant,
    TournamentStatus,
    User,
)
from app.services.rating import RatingRow


def image_url(path: str | None) -> str | None:
    return f"/uploads/{path}" if path else None


def player_brief(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": image_url(user.avatar_path),
        "status": user.status.value,
    }


def account_out(user: User) -> dict:
    return {
        "id": user.id,
        "login": user.login,
        "nickname": user.nickname,
        "role": user.role.value,
        "status": user.status.value,
        "avatar_url": image_url(user.avatar_path),
        "full_body_url": image_url(user.full_body_path),
        "rating_points": user.rating_points,
        "onboarded": user.onboarded_at is not None,
    }


def belt_brief(belt: Belt) -> dict:
    return {"id": belt.id, "name": belt.name, "kind": belt.kind.value, "icon_url": image_url(belt.icon_path)}


def belt_out(belt: Belt) -> dict:
    return {**belt_brief(belt), "champion": player_brief(belt.current_champion)}


def _belt_win_out(win: BeltWin) -> dict:
    return {
        "id": win.id,
        "won_at": win.won_at,
        "player": player_brief(win.user),
        "is_defense": win.is_defense,
        "fight_id": win.fight_id,
        "tournament": {"id": win.tournament.id, "title": win.tournament.title} if win.tournament else None,
        "title_fight_id": win.title_fight_id,
    }


def belt_detail(db: Session, belt: Belt) -> dict:
    wins = db.scalars(
        select(BeltWin).where(BeltWin.belt_id == belt.id).order_by(BeltWin.won_at.desc(), BeltWin.id.desc())
    ).all()
    return {**belt_out(belt), "history": [_belt_win_out(win) for win in wins]}


def past_belt_caption(belt: Belt, wins: list[BeltWin]) -> str:
    if all(win.awarded_by_id for win in wins):
        return f"Бывший обладатель пояса „{belt.name}“"
    if belt.kind == BeltKind.MAIN:
        return f"Победитель титульного боя за пояс „{belt.name}“"
    return f"Победитель турнира за пояс „{belt.name}“"


def player_belts(db: Session, user: User) -> dict:
    wins = db.scalars(
        select(BeltWin).where(BeltWin.user_id == user.id).order_by(BeltWin.won_at.desc(), BeltWin.id.desc())
    ).all()
    by_belt: dict[int, list[BeltWin]] = {}
    for win in wins:
        by_belt.setdefault(win.belt_id, []).append(win)

    active, past = [], []
    for belt_wins in by_belt.values():
        belt = belt_wins[0].belt
        is_current = belt.current_champion_id == user.id
        entry = {
            "belt": belt_brief(belt),
            "caption": "Действующий чемпион" if is_current else past_belt_caption(belt, belt_wins),
            "wins": [_belt_win_out(win) for win in belt_wins],
        }
        (active if is_current else past).append(entry)
    return {"active": active, "past": past}


def _adjustment_out(adjustment: RatingAdjustment | None) -> dict | None:
    if adjustment is None or adjustment.status != AdjustmentStatus.ACTIVE:
        return None
    return {
        "winner_delta": adjustment.winner_delta,
        "loser_delta": -adjustment.winner_delta,
        "reason": adjustment.reason,
        "version": adjustment.version,
    }


def _fighter_out(user: User) -> dict:
    return {**player_brief(user), "full_body_url": image_url(user.full_body_path)}


def _points_change(fight: Fight) -> list[int] | None:
    """Итог очков за бой с учётом ручной корректировки, в порядке player1, player2."""
    if not fight.rating_changes:
        return None
    adjustment = _adjustment_out(fight.adjustment)
    totals: dict[int, int] = {}
    for change in fight.rating_changes:
        manual = 0
        if adjustment:
            manual = adjustment["winner_delta"] if change.player_id == fight.winner_id else adjustment["loser_delta"]
        totals[change.player_id] = change.delta + manual
    return [totals[fight.player1_id], totals[fight.player2_id]]


def _votes_out(votes: list, first_id: int, second_id: int, viewer: User) -> dict:
    counts = Counter(vote.voted_for_id for vote in votes)
    my_vote = next((vote.voted_for_id for vote in votes if vote.voter_id == viewer.id), None)
    return {"first": counts[first_id], "second": counts[second_id], "my_vote": my_vote}


def _fight_votes(fight: Fight, viewer: User) -> dict | None:
    """Голоса собираются до боя, поэтому лежат у его источника. У боя без него голосования не было."""
    origin = fight.planned or fight.title_fight or fight.match
    if origin is None:
        return None
    return _votes_out(origin.votes, fight.player1_id, fight.player2_id, viewer)


def _version_out(version) -> dict:
    return {
        "version_no": version.version_no,
        "submitted_by": player_brief(version.submitted_by),
        "fought_at": version.fought_at,
        "winner": player_brief(version.winner),
        "method": version.method.value if version.method else None,
        "round": version.round_no,
        "dispute_reason": version.dispute_reason,
        "disputed_by": player_brief(version.disputed_by),
        "disputed_at": version.disputed_at,
        "created_at": version.created_at,
        "confirmed_by": [player_brief(c.player) for c in version.confirmations],
    }


def fight_brief(fight: Fight, viewer: User) -> dict:
    version = fight.current_version
    confirmed_ids = {c.player_id for c in version.confirmations}
    awaits_viewer = (
        fight.has_player(viewer.id) and fight.status == FightStatus.PENDING and viewer.id not in confirmed_ids
    )
    tournament = fight.match.tournament if fight.match else None
    return {
        "id": fight.id,
        "kind": fight.kind.value,
        "status": fight.status.value,
        "version_no": fight.current_version_no,
        "player1": _fighter_out(fight.player1),
        "player2": _fighter_out(fight.player2),
        "initiator_id": fight.initiator_id,
        "fought_at": fight.fought_at,
        "winner_id": fight.winner_id,
        "method": fight.method.value if fight.method else None,
        "round": fight.round_no,
        "confirmed_at": fight.confirmed_at,
        "points_change": _points_change(fight),
        "votes": _fight_votes(fight, viewer),
        "tournament": {"id": tournament.id, "title": tournament.title} if tournament else None,
        "title_fight_id": fight.title_fight_id,
        "can_confirm": awaits_viewer,
        "can_dispute": awaits_viewer and version.submitted_by_id != viewer.id,
        "can_correct": fight.status == FightStatus.DISPUTED and fight.initiator_id == viewer.id,
        "dispute_reason": version.dispute_reason if fight.status == FightStatus.DISPUTED else None,
    }


def _rating_change_out(change) -> dict:
    return {
        "player": player_brief(change.player),
        "place_before": change.place_before,
        "points_before": change.points_before,
        "delta": change.delta,
        "loss_discount": change.loss_discount,
        "points_after": change.points_after,
        "place_after": change.place_after,
        "table_place_before": change.table_place_before,
        "table_place_after": change.table_place_after,
        "champion_before": change.champion_before,
        "champion_after": change.champion_after,
    }


def fight_detail(fight: Fight, viewer: User) -> dict:
    return {
        **fight_brief(fight, viewer),
        "versions": [_version_out(version) for version in fight.versions],
        "rating_changes": [_rating_change_out(change) for change in fight.rating_changes],
        "adjustment": _adjustment_out(fight.adjustment),
        "is_title_defense": fight.title_fight.is_defense if fight.title_fight else None,
        "resolution": resolution_out(fight),
    }


def stats_with_leaders(stats: dict) -> dict:
    return {
        **stats,
        "nemeses": [{"player": player_brief(user), "count": count} for user, count in stats["nemeses"]],
        "victims": [{"player": player_brief(user), "count": count} for user, count in stats["victims"]],
    }


def rating_row_out(row: RatingRow, viewer: User) -> dict:
    # Спецместо видно только админу и владельцу. Место по очкам скрыто вместе с ним:
    # по расхождению с номером в таблице закрепление легко вычислить.
    return {
        "player": player_brief(row.user),
        "points": row.user.rating_points,
        "points_place": row.points_place if viewer.is_staff else None,
        "display_place": row.display_place,
        "is_special": row.is_special if viewer.is_staff else False,
        "is_champion": row.is_champion,
        "is_calibrating": row.is_calibrating,
    }


def _seat_counts(db: Session, tournament_ids: list[int]) -> dict[int, int]:
    return dict(
        db.execute(
            select(TournamentParticipant.tournament_id, func.count())
            .where(TournamentParticipant.tournament_id.in_(tournament_ids))
            .group_by(TournamentParticipant.tournament_id)
        ).all()
    )


def _joined_ids(db: Session, tournament_ids: list[int], viewer: User) -> set[int]:
    return set(
        db.scalars(
            select(TournamentParticipant.tournament_id).where(
                TournamentParticipant.tournament_id.in_(tournament_ids), TournamentParticipant.user_id == viewer.id
            )
        )
    )


def tournament_cards(db: Session, tournaments: list[Tournament], viewer: User) -> list[dict]:
    ids = [tournament.id for tournament in tournaments]
    seats = _seat_counts(db, ids)
    joined = _joined_ids(db, ids, viewer)
    return [
        {
            "id": tournament.id,
            "title": tournament.title,
            "description": tournament.description,
            "status": tournament.status.value,
            "capacity": tournament.capacity,
            "win_points": tournament.win_points,
            "seats_taken": seats.get(tournament.id, 0),
            "belt": belt_brief(tournament.belt),
            "winner": player_brief(tournament.winner),
            "is_participant": tournament.id in joined,
            "cancel_reason": tournament.cancel_reason,
            "started_at": tournament.started_at,
            "finished_at": tournament.finished_at,
        }
        for tournament in tournaments
    ]


def round_name(round_no: int, rounds_count: int) -> str:
    left = rounds_count - round_no
    if left == 0:
        return "Финал"
    if left == 1:
        return "Полуфинал"
    if left == 2:
        return "Четвертьфинал"
    return f"1/{2 ** left} финала"


def match_state(match: TournamentMatch) -> str:
    if match.is_bye:
        return "bye"
    if match.winner_id is not None:
        return "completed"
    if match.fight is not None:
        return match.fight.status.value
    if match.player1_id is not None and match.player2_id is not None:
        return "ready"
    return "waiting_players"


def match_out(match: TournamentMatch, viewer: User) -> dict:
    tournament = match.tournament
    state = match_state(match)
    is_player = viewer.id in (match.player1_id, match.player2_id)
    return {
        "id": match.id,
        "round": match.round,
        "position": match.position,
        "player1": player_brief(match.player1),
        "player2": player_brief(match.player2),
        "winner_id": match.winner_id,
        "is_bye": match.is_bye,
        "state": state,
        "fight_id": match.fight.id if match.fight else None,
        "can_submit": is_player and state == "ready" and tournament.status == TournamentStatus.IN_PROGRESS,
        "tournament": {"id": tournament.id, "title": tournament.title},
        "round_name": round_name(match.round, tournament.rounds_count or match.round),
    }


def upcoming_out(kind: str, target, viewer: User) -> dict:
    is_player = viewer.id in (target.player1_id, target.player2_id)
    is_tournament = kind == "tournament"
    return {
        "kind": kind,
        "id": target.id,
        "player1": _fighter_out(target.player1),
        "player2": _fighter_out(target.player2),
        "scheduled_at": getattr(target, "scheduled_at", None),
        "tournament": {"id": target.tournament.id, "title": target.tournament.title} if is_tournament else None,
        "round_name": round_name(target.round, target.tournament.rounds_count or target.round) if is_tournament else None,
        "votes": _votes_out(target.votes, target.player1_id, target.player2_id, viewer),
        "can_vote": not is_player,
        "can_submit": is_player,
        "can_cancel": kind == "planned" and (is_player or viewer.is_staff),
    }


def tournament_detail(db: Session, tournament: Tournament, viewer: User) -> dict:
    card = tournament_cards(db, [tournament], viewer)[0]
    rounds: list[dict] = []
    for match in tournament.matches:
        if not rounds or rounds[-1]["round"] != match.round:
            rounds.append(
                {
                    "round": match.round,
                    "name": round_name(match.round, tournament.rounds_count or match.round),
                    "matches": [],
                }
            )
        rounds[-1]["matches"].append(match_out(match, viewer))
    return {
        **card,
        "participants": [player_brief(p.user) for p in tournament.participants],
        "rounds": rounds,
    }


def title_fight_out(title_fight: TitleFight, viewer: User) -> dict:
    fight = title_fight.fight
    is_player = viewer.id in (title_fight.player1_id, title_fight.player2_id)
    return {
        "id": title_fight.id,
        "belt": belt_brief(title_fight.belt),
        "player1": player_brief(title_fight.player1),
        "player2": player_brief(title_fight.player2),
        "champion_id": title_fight.champion_id,
        "scheduled_at": title_fight.scheduled_at,
        "status": title_fight.status.value,
        "winner": player_brief(title_fight.winner),
        "is_defense": title_fight.is_defense,
        "cancel_reason": title_fight.cancel_reason,
        "created_at": title_fight.created_at,
        "fight": fight_brief(fight, viewer) if fight else None,
        "can_submit": is_player and title_fight.status == TitleFightStatus.SCHEDULED and fight is None,
    }


def promo_out(db: Session, promo: Promo, viewer: User) -> dict:
    tournament = None
    if promo.tournament is not None:
        tournament = tournament_cards(db, [promo.tournament], viewer)[0]
    return {
        "id": promo.id,
        "type": promo.type.value,
        "title": promo.title,
        "description": promo.description,
        "image_url": image_url(promo.image_path),
        "tournament": tournament,
        "fighter1": player_brief(promo.fighter1),
        "fighter2": player_brief(promo.fighter2),
        "fight_at": promo.fight_at,
        "player": player_brief(promo.player),
        "is_published": promo.is_published,
        "show_from": promo.show_from,
        "show_until": promo.show_until,
        "sort_order": promo.sort_order,
    }


def admin_user_out(user: User, special: SpecialPlace | None = None) -> dict:
    return {**account_out(user), "created_at": user.created_at, "special_place": special.place if special else None}


def resolution_out(fight: Fight) -> dict | None:
    if fight.resolved_by_id is None:
        return None
    return {
        "by": player_brief(fight.resolved_by),
        "reason": fight.resolution_reason,
        "at": fight.resolved_at,
        "accepted": fight.status == FightStatus.CONFIRMED,
    }
