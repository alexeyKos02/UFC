"""tournament prize snapshots for the rating chart and manual point grants by staff

tournament_prize_changes — очки и номер в таблице до и после приза за 1–3-е место турнира
(пишет пересчёт, нужен для графика в профиле). point_grants — очки, которые админ или владелец
начислил или снял вручную с причиной; событие пересчёта по дате начисления.
История пересчитывается целиком, чтобы заполнить снимки призов уже завершённых турниров.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

from app.services import recalc


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tournament_prize_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tournament_id', sa.Integer(), nullable=False),
        sa.Column('fight_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('place', sa.Integer(), nullable=False),
        sa.Column('points_before', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('points_after', sa.Integer(), nullable=False),
        sa.Column('table_place_before', sa.Integer(), nullable=True),
        sa.Column('table_place_after', sa.Integer(), nullable=True),
        sa.Column('champion_before', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('champion_after', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['fight_id'], ['fights.id'], name=op.f('fk_tournament_prize_changes_fight_id_fights'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['player_id'], ['users.id'], name=op.f('fk_tournament_prize_changes_player_id_users')
        ),
        sa.ForeignKeyConstraint(
            ['tournament_id'],
            ['tournaments.id'],
            name=op.f('fk_tournament_prize_changes_tournament_id_tournaments'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tournament_prize_changes')),
        sa.UniqueConstraint('fight_id', 'player_id', name='uq_tournament_prize_changes_fight_player'),
    )
    op.create_index(
        op.f('ix_tournament_prize_changes_fight_id'), 'tournament_prize_changes', ['fight_id'], unique=False
    )
    op.create_index(
        op.f('ix_tournament_prize_changes_player_id'), 'tournament_prize_changes', ['player_id'], unique=False
    )
    op.create_index(
        op.f('ix_tournament_prize_changes_tournament_id'), 'tournament_prize_changes', ['tournament_id'], unique=False
    )

    op.create_table(
        'point_grants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'cancelled', name='point_grant_status', native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cancelled_by_id', sa.Integer(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_reason', sa.Text(), nullable=True),
        sa.Column('points_before', sa.Integer(), nullable=True),
        sa.Column('points_after', sa.Integer(), nullable=True),
        sa.Column('table_place_before', sa.Integer(), nullable=True),
        sa.Column('table_place_after', sa.Integer(), nullable=True),
        sa.Column('champion_before', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('champion_after', sa.Boolean(), server_default='false', nullable=False),
        sa.CheckConstraint('delta <> 0', name=op.f('ck_point_grants_delta_not_zero')),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], name=op.f('fk_point_grants_player_id_users')),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_point_grants_created_by_id_users')),
        sa.ForeignKeyConstraint(
            ['cancelled_by_id'], ['users.id'], name=op.f('fk_point_grants_cancelled_by_id_users')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_point_grants')),
    )
    op.create_index(op.f('ix_point_grants_player_id'), 'point_grants', ['player_id'], unique=False)

    recalc.recalculate(op.get_bind())


def downgrade() -> None:
    op.drop_index(op.f('ix_point_grants_player_id'), table_name='point_grants')
    op.drop_table('point_grants')
    op.drop_index(op.f('ix_tournament_prize_changes_tournament_id'), table_name='tournament_prize_changes')
    op.drop_index(op.f('ix_tournament_prize_changes_player_id'), table_name='tournament_prize_changes')
    op.drop_index(op.f('ix_tournament_prize_changes_fight_id'), table_name='tournament_prize_changes')
    op.drop_table('tournament_prize_changes')
