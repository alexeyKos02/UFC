"""tournament win points

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tournaments', sa.Column('win_points', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_tournaments_win_points_non_negative'), 'tournaments', 'win_points >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_tournaments_win_points_non_negative'), 'tournaments', type_='check')
    op.drop_column('tournaments', 'win_points')
