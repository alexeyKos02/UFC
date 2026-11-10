"""planned fights, votes and place after fight

Revision ID: 0002
Revises: 0001
"""
from itertools import groupby

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def _backfill_place_after() -> None:
    """Восстанавливает места после уже подтверждённых боёв, проигрывая снимки очков по порядку.

    Блокировки в прошлом не восстановить, поэтому в расчёт идут все, кто уже был зарегистрирован.
    """
    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, created_at FROM users")).all()
    changes = bind.execute(
        sa.text(
            "SELECT rc.id, rc.fight_id, rc.player_id, rc.points_after, f.confirmed_at "
            "FROM rating_changes rc JOIN fights f ON f.id = rc.fight_id "
            "ORDER BY f.confirmed_at, f.id, rc.id"
        )
    ).all()
    points = {user.id: 100 for user in users}
    registered_at = {user.id: user.created_at for user in users}
    for _, group in groupby(changes, key=lambda change: change.fight_id):
        fight_changes = list(group)
        for change in fight_changes:
            points[change.player_id] = change.points_after
        moment = fight_changes[0].confirmed_at
        present = {value for user_id, value in points.items() if registered_at[user_id] <= moment}
        place_by_points = {value: place for place, value in enumerate(sorted(present, reverse=True), start=1)}
        for change in fight_changes:
            bind.execute(
                sa.text("UPDATE rating_changes SET place_after = :place WHERE id = :id"),
                {"place": place_by_points[change.points_after], "id": change.id},
            )


def upgrade() -> None:
    op.add_column('rating_changes', sa.Column('place_after', sa.Integer(), nullable=True))
    _backfill_place_after()
    op.alter_column('rating_changes', 'place_after', nullable=False)

    op.create_table('planned_fights',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player1_id', sa.Integer(), nullable=False),
    sa.Column('player2_id', sa.Integer(), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('scheduled', 'cancelled', name='planned_fight_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=False),
    sa.Column('client_request_id', sa.String(length=36), nullable=False),
    sa.Column('cancelled_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('player1_id <> player2_id', name=op.f('ck_planned_fights_different_players')),
    sa.ForeignKeyConstraint(['cancelled_by_id'], ['users.id'], name=op.f('fk_planned_fights_cancelled_by_id_users')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_planned_fights_created_by_id_users')),
    sa.ForeignKeyConstraint(['player1_id'], ['users.id'], name=op.f('fk_planned_fights_player1_id_users')),
    sa.ForeignKeyConstraint(['player2_id'], ['users.id'], name=op.f('fk_planned_fights_player2_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_planned_fights')),
    sa.UniqueConstraint('created_by_id', 'client_request_id', name='uq_planned_fights_creator_request')
    )
    op.create_index(op.f('ix_planned_fights_player1_id'), 'planned_fights', ['player1_id'], unique=False)
    op.create_index(op.f('ix_planned_fights_player2_id'), 'planned_fights', ['player2_id'], unique=False)
    op.create_index(op.f('ix_planned_fights_status'), 'planned_fights', ['status'], unique=False)

    op.add_column('fights', sa.Column('planned_fight_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_fights_planned_fight_id_planned_fights'), 'fights', 'planned_fights', ['planned_fight_id'], ['id'])
    op.create_unique_constraint(op.f('uq_fights_planned_fight_id'), 'fights', ['planned_fight_id'])

    op.create_table('fight_votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('voter_id', sa.Integer(), nullable=False),
    sa.Column('voted_for_id', sa.Integer(), nullable=False),
    sa.Column('planned_fight_id', sa.Integer(), nullable=True),
    sa.Column('title_fight_id', sa.Integer(), nullable=True),
    sa.Column('tournament_match_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('num_nonnulls(planned_fight_id, title_fight_id, tournament_match_id) = 1', name=op.f('ck_fight_votes_single_target')),
    sa.ForeignKeyConstraint(['planned_fight_id'], ['planned_fights.id'], name=op.f('fk_fight_votes_planned_fight_id_planned_fights')),
    sa.ForeignKeyConstraint(['title_fight_id'], ['title_fights.id'], name=op.f('fk_fight_votes_title_fight_id_title_fights')),
    sa.ForeignKeyConstraint(['tournament_match_id'], ['tournament_matches.id'], name=op.f('fk_fight_votes_tournament_match_id_tournament_matches')),
    sa.ForeignKeyConstraint(['voted_for_id'], ['users.id'], name=op.f('fk_fight_votes_voted_for_id_users')),
    sa.ForeignKeyConstraint(['voter_id'], ['users.id'], name=op.f('fk_fight_votes_voter_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fight_votes')),
    sa.UniqueConstraint('voter_id', 'planned_fight_id', name='uq_fight_votes_planned'),
    sa.UniqueConstraint('voter_id', 'title_fight_id', name='uq_fight_votes_title'),
    sa.UniqueConstraint('voter_id', 'tournament_match_id', name='uq_fight_votes_match')
    )
    op.create_index(op.f('ix_fight_votes_planned_fight_id'), 'fight_votes', ['planned_fight_id'], unique=False)
    op.create_index(op.f('ix_fight_votes_title_fight_id'), 'fight_votes', ['title_fight_id'], unique=False)
    op.create_index(op.f('ix_fight_votes_tournament_match_id'), 'fight_votes', ['tournament_match_id'], unique=False)


def downgrade() -> None:
    op.drop_table('fight_votes')
    op.drop_constraint(op.f('uq_fights_planned_fight_id'), 'fights', type_='unique')
    op.drop_constraint(op.f('fk_fights_planned_fight_id_planned_fights'), 'fights', type_='foreignkey')
    op.drop_column('fights', 'planned_fight_id')
    op.drop_table('planned_fights')
    op.drop_column('rating_changes', 'place_after')
