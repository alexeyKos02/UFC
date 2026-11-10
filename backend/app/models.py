from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class UserRole(StrEnum):
    PLAYER = "player"
    ADMIN = "admin"
    OWNER = "owner"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class FightKind(StrEnum):
    REGULAR = "regular"
    TOURNAMENT = "tournament"
    TITLE = "title"


class FightStatus(StrEnum):
    PENDING = "pending"
    DISPUTED = "disputed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class FightMethod(StrEnum):
    KO_TKO = "ko_tko"
    SUBMISSION = "submission"
    DECISION = "decision"


class TournamentStatus(StrEnum):
    DRAFT = "draft"
    REGISTRATION = "registration"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class BeltKind(StrEnum):
    MAIN = "main"
    TOURNAMENT = "tournament"


class TitleFightStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PromoType(StrEnum):
    TOURNAMENT = "tournament"
    FIGHT_ANNOUNCEMENT = "fight_announcement"
    FIGHTER_OF_WEEK = "fighter_of_week"


class AdjustmentStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class AdjustmentAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"


class SpecialPlaceAction(StrEnum):
    SET = "set"
    CHANGE = "change"
    CLEAR = "clear"


def enum_type(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_nickname_lower", text("lower(nickname)"), unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, "user_role"), default=UserRole.PLAYER)
    status: Mapped[UserStatus] = mapped_column(enum_type(UserStatus, "user_status"), default=UserStatus.ACTIVE)
    nickname: Mapped[str] = mapped_column(String(32))
    avatar_path: Mapped[str | None] = mapped_column(String(255))
    full_body_path: Mapped[str | None] = mapped_column(String(255))
    rating_points: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    created_at: Mapped[datetime] = created_at_column()

    @property
    def is_staff(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.OWNER)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship()


class Belt(Base):
    __tablename__ = "belts"
    __table_args__ = (
        Index("uq_belts_single_main", "kind", unique=True, postgresql_where=text("kind = 'main'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[BeltKind] = mapped_column(enum_type(BeltKind, "belt_kind"))
    name: Mapped[str] = mapped_column(String(100))
    icon_path: Mapped[str | None] = mapped_column(String(255))
    current_champion_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    current_champion: Mapped[User | None] = relationship()


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("capacity >= 2", name="capacity_min"),
        Index(
            "uq_tournaments_active_belt",
            "belt_id",
            unique=True,
            postgresql_where=text("status IN ('registration', 'in_progress')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    capacity: Mapped[int] = mapped_column(Integer)
    belt_id: Mapped[int] = mapped_column(ForeignKey("belts.id"), index=True)
    status: Mapped[TournamentStatus] = mapped_column(
        enum_type(TournamentStatus, "tournament_status"), default=TournamentStatus.DRAFT, index=True
    )
    rounds_count: Mapped[int | None] = mapped_column(Integer)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    belt: Mapped[Belt] = relationship()
    winner: Mapped[User | None] = relationship(foreign_keys=[winner_id])
    participants: Mapped[list["TournamentParticipant"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan", order_by="TournamentParticipant.id"
    )
    matches: Mapped[list["TournamentMatch"]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
        order_by="(TournamentMatch.round, TournamentMatch.position)",
    )


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_tournament_participant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[datetime] = created_at_column()

    tournament: Mapped[Tournament] = relationship(back_populates="participants")
    user: Mapped[User] = relationship()


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"
    __table_args__ = (
        UniqueConstraint("tournament_id", "round", "position", name="uq_tournament_match_slot"),
        CheckConstraint(
            "player1_id IS NULL OR player2_id IS NULL OR player1_id <> player2_id", name="different_players"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    player1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    player2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_bye: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    tournament: Mapped[Tournament] = relationship(back_populates="matches")
    player1: Mapped[User | None] = relationship(foreign_keys=[player1_id])
    player2: Mapped[User | None] = relationship(foreign_keys=[player2_id])
    winner: Mapped[User | None] = relationship(foreign_keys=[winner_id])
    fight: Mapped["Fight | None"] = relationship(back_populates="match", uselist=False)


class TitleFight(Base):
    __tablename__ = "title_fights"
    __table_args__ = (
        CheckConstraint("player1_id <> player2_id", name="different_players"),
        Index("uq_title_fights_open", "belt_id", unique=True, postgresql_where=text("status = 'scheduled'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    belt_id: Mapped[int] = mapped_column(ForeignKey("belts.id"), index=True)
    player1_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    player2_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    champion_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TitleFightStatus] = mapped_column(
        enum_type(TitleFightStatus, "title_fight_status"), default=TitleFightStatus.SCHEDULED, index=True
    )
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_defense: Mapped[bool | None] = mapped_column(Boolean)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    belt: Mapped[Belt] = relationship()
    player1: Mapped[User] = relationship(foreign_keys=[player1_id])
    player2: Mapped[User] = relationship(foreign_keys=[player2_id])
    champion: Mapped[User | None] = relationship(foreign_keys=[champion_id])
    winner: Mapped[User | None] = relationship(foreign_keys=[winner_id])
    fight: Mapped["Fight | None"] = relationship(back_populates="title_fight", uselist=False)


class Fight(Base):
    """Запись боя. Поля результата повторяют текущую версию, история лежит в FightVersion."""

    __tablename__ = "fights"
    __table_args__ = (
        CheckConstraint("player1_id <> player2_id", name="different_players"),
        CheckConstraint("winner_id IN (player1_id, player2_id)", name="winner_in_pair"),
        CheckConstraint("loser_id IN (player1_id, player2_id)", name="loser_in_pair"),
        CheckConstraint("winner_id <> loser_id", name="winner_not_loser"),
        UniqueConstraint("initiator_id", "client_request_id", name="uq_fights_initiator_request"),
        Index("ix_fights_confirmed_order", "fought_at", "id", postgresql_where=text("status = 'confirmed'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[FightKind] = mapped_column(enum_type(FightKind, "fight_kind"))
    status: Mapped[FightStatus] = mapped_column(enum_type(FightStatus, "fight_status"), default=FightStatus.PENDING)
    player1_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    player2_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    initiator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    client_request_id: Mapped[str | None] = mapped_column(String(36))
    current_version_no: Mapped[int] = mapped_column(Integer, default=1)
    fought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    winner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    loser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    method: Mapped[FightMethod | None] = mapped_column(enum_type(FightMethod, "fight_method"))
    round_no: Mapped[int | None] = mapped_column(Integer)
    tournament_match_id: Mapped[int | None] = mapped_column(ForeignKey("tournament_matches.id"), unique=True)
    title_fight_id: Mapped[int | None] = mapped_column(ForeignKey("title_fights.id"), unique=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    player1: Mapped[User] = relationship(foreign_keys=[player1_id])
    player2: Mapped[User] = relationship(foreign_keys=[player2_id])
    initiator: Mapped[User] = relationship(foreign_keys=[initiator_id])
    winner: Mapped[User] = relationship(foreign_keys=[winner_id])
    loser: Mapped[User] = relationship(foreign_keys=[loser_id])
    versions: Mapped[list["FightVersion"]] = relationship(
        back_populates="fight", cascade="all, delete-orphan", order_by="FightVersion.version_no"
    )
    rating_changes: Mapped[list["RatingChange"]] = relationship(
        back_populates="fight", cascade="all, delete-orphan", order_by="RatingChange.id"
    )
    adjustment: Mapped["RatingAdjustment | None"] = relationship(back_populates="fight", uselist=False)
    match: Mapped[TournamentMatch | None] = relationship(back_populates="fight")
    title_fight: Mapped[TitleFight | None] = relationship(back_populates="fight")

    @property
    def current_version(self) -> "FightVersion":
        return next(v for v in self.versions if v.version_no == self.current_version_no)

    def opponent_id(self, player_id: int) -> int:
        return self.player2_id if self.player1_id == player_id else self.player1_id

    def has_player(self, player_id: int) -> bool:
        return player_id in (self.player1_id, self.player2_id)


class FightVersion(Base):
    __tablename__ = "fight_versions"
    __table_args__ = (UniqueConstraint("fight_id", "version_no", name="uq_fight_version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fight_id: Mapped[int] = mapped_column(ForeignKey("fights.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    winner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    method: Mapped[FightMethod | None] = mapped_column(enum_type(FightMethod, "fight_version_method"))
    round_no: Mapped[int | None] = mapped_column(Integer)
    dispute_reason: Mapped[str | None] = mapped_column(Text)
    disputed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    fight: Mapped[Fight] = relationship(back_populates="versions")
    submitted_by: Mapped[User] = relationship(foreign_keys=[submitted_by_id])
    winner: Mapped[User] = relationship(foreign_keys=[winner_id])
    disputed_by: Mapped[User | None] = relationship(foreign_keys=[disputed_by_id])
    confirmations: Mapped[list["FightConfirmation"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="FightConfirmation.id"
    )


class FightConfirmation(Base):
    __tablename__ = "fight_confirmations"
    __table_args__ = (UniqueConstraint("version_id", "player_id", name="uq_fight_confirmation_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("fight_versions.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()

    version: Mapped[FightVersion] = relationship(back_populates="confirmations")
    player: Mapped[User] = relationship()


class RatingChange(Base):
    """Автоматическое начисление: снимок места и очков игрока до расчёта и итог."""

    __tablename__ = "rating_changes"
    __table_args__ = (UniqueConstraint("fight_id", "player_id", name="uq_rating_change_fight_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fight_id: Mapped[int] = mapped_column(ForeignKey("fights.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    place_before: Mapped[int] = mapped_column(Integer)
    points_before: Mapped[int] = mapped_column(Integer)
    delta: Mapped[int] = mapped_column(Integer)
    points_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()

    fight: Mapped[Fight] = relationship(back_populates="rating_changes")
    player: Mapped[User] = relationship()


class RatingAdjustment(Base):
    """Действующая ручная корректировка боя. winner_delta положительна, если очки ушли победителю."""

    __tablename__ = "rating_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    fight_id: Mapped[int] = mapped_column(ForeignKey("fights.id", ondelete="CASCADE"), unique=True)
    status: Mapped[AdjustmentStatus] = mapped_column(enum_type(AdjustmentStatus, "adjustment_status"))
    winner_delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    fight: Mapped[Fight] = relationship(back_populates="adjustment")


class RatingAdjustmentLog(Base):
    __tablename__ = "rating_adjustment_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    fight_id: Mapped[int] = mapped_column(ForeignKey("fights.id", ondelete="CASCADE"), index=True)
    action: Mapped[AdjustmentAction] = mapped_column(enum_type(AdjustmentAction, "adjustment_action"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    winner_delta_before: Mapped[int] = mapped_column(Integer)
    winner_delta_after: Mapped[int] = mapped_column(Integer)
    winner_points_before: Mapped[int] = mapped_column(Integer)
    winner_points_after: Mapped[int] = mapped_column(Integer)
    loser_points_before: Mapped[int] = mapped_column(Integer)
    loser_points_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()

    fight: Mapped[Fight] = relationship()
    actor: Mapped[User] = relationship()


class SpecialPlace(Base):
    __tablename__ = "special_places"
    __table_args__ = (CheckConstraint("place >= 1", name="place_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    place: Mapped[int] = mapped_column(Integer, unique=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(foreign_keys=[user_id])


class SpecialPlaceLog(Base):
    __tablename__ = "special_place_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[SpecialPlaceAction] = mapped_column(enum_type(SpecialPlaceAction, "special_place_action"))
    place_before: Mapped[int | None] = mapped_column(Integer)
    place_after: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    actor: Mapped[User] = relationship(foreign_keys=[actor_id])


class BeltWin(Base):
    __tablename__ = "belt_wins"
    __table_args__ = (
        UniqueConstraint("fight_id", name="uq_belt_wins_fight"),
        UniqueConstraint("tournament_id", name="uq_belt_wins_tournament"),
        UniqueConstraint("title_fight_id", name="uq_belt_wins_title_fight"),
        CheckConstraint("(tournament_id IS NULL) <> (title_fight_id IS NULL)", name="single_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    belt_id: Mapped[int] = mapped_column(ForeignKey("belts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    fight_id: Mapped[int] = mapped_column(ForeignKey("fights.id"))
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id"))
    title_fight_id: Mapped[int | None] = mapped_column(ForeignKey("title_fights.id"))
    previous_champion_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_defense: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    won_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    belt: Mapped[Belt] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    fight: Mapped[Fight] = relationship()
    tournament: Mapped[Tournament | None] = relationship()
    title_fight: Mapped[TitleFight | None] = relationship()


class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[PromoType] = mapped_column(enum_type(PromoType, "promo_type"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    image_path: Mapped[str | None] = mapped_column(String(255))
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    fighter1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    fighter2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    fight_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    show_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    show_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    tournament: Mapped[Tournament | None] = relationship()
    fighter1: Mapped[User | None] = relationship(foreign_keys=[fighter1_id])
    fighter2: Mapped[User | None] = relationship(foreign_keys=[fighter2_id])
    player: Mapped[User | None] = relationship(foreign_keys=[player_id])
