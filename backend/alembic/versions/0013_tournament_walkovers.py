"""tournament matches: technical win when the opponent does not show up

Победителя назначает админ или владелец, боя нет: в статистику и очки лиги исход не идёт.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tournament_matches', sa.Column('walkover_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tournament_matches', sa.Column('walkover_by_id', sa.Integer(), nullable=True))
    op.add_column('tournament_matches', sa.Column('walkover_reason', sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f('fk_tournament_matches_walkover_by_id_users'), 'tournament_matches', 'users', ['walkover_by_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_tournament_matches_walkover_by_id_users'), 'tournament_matches', type_='foreignkey')
    op.drop_column('tournament_matches', 'walkover_reason')
    op.drop_column('tournament_matches', 'walkover_by_id')
    op.drop_column('tournament_matches', 'walkover_at')
