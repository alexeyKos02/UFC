"""Бои без итога: кто должен сделать следующий шаг.

Подтверждать бои можно в любом порядке. Очки считаются по дате боя (app/services/recalc.py):
если подтвердили бой, сыгранный раньше уже подтверждённых, следующие бои пересчитываются.
"""

from app.models import Fight, FightStatus

OPEN_STATUSES = (FightStatus.PENDING, FightStatus.DISPUTED)


def waiting_for(fight: Fight) -> list[int]:
    """Кто должен сделать следующий шаг по бою без итога."""
    if fight.status == FightStatus.DISPUTED:
        return [fight.initiator_id]
    confirmed = {item.player_id for item in fight.current_version.confirmations}
    return [player_id for player_id in (fight.player1_id, fight.player2_id) if player_id not in confirmed]
