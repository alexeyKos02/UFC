from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.models import FightMethod, PromoType

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
BeltName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Nickname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=32)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class CredentialsIn(BaseModel):
    login: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ProfileIn(BaseModel):
    nickname: Nickname


class FightResultIn(BaseModel):
    fought_at: AwareDatetime
    winner_id: int
    method: FightMethod | None = None
    round: int | None = Field(default=None, ge=1, le=5)


class FightCreateIn(FightResultIn):
    opponent_id: int
    client_request_id: UUID


class PlannedFightIn(BaseModel):
    opponent_id: int
    scheduled_at: AwareDatetime
    client_request_id: UUID


class VoteIn(BaseModel):
    player_id: int


class FightVersionRef(BaseModel):
    version_no: int


class FightDisputeIn(FightVersionRef):
    reason: Reason


class FightCorrectIn(FightResultIn):
    expected_version: int


class TournamentIn(BaseModel):
    title: Title
    description: Description = ""
    capacity: int = Field(ge=2, le=128)
    win_points: int = Field(ge=0, le=100_000)
    belt_id: int


class CancelIn(BaseModel):
    reason: Reason


class BeltIn(BaseModel):
    name: BeltName


class BeltAwardIn(BaseModel):
    player_id: int


class TitleFightIn(BaseModel):
    player1_id: int | None = None
    player2_id: int
    scheduled_at: AwareDatetime | None = None


class RoleIn(BaseModel):
    role: str


class AdjustmentIn(BaseModel):
    player_id: int
    points: int = Field(ge=-100_000, le=100_000)
    reason: Reason
    expected_version: int = Field(ge=0)


class AdjustmentCancelIn(BaseModel):
    reason: Reason
    expected_version: int = Field(ge=1)


class SpecialPlaceIn(BaseModel):
    place: int


class PromoIn(BaseModel):
    type: PromoType
    title: Title
    description: Description = ""
    tournament_id: int | None = None
    fighter1_id: int | None = None
    fighter2_id: int | None = None
    fight_at: AwareDatetime | None = None
    player_id: int | None = None
    show_from: AwareDatetime | None = None
    show_until: AwareDatetime | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)


class PublishIn(BaseModel):
    published: bool
