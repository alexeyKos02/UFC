"""users.onboarded_at: when the player finished the first-visit tour

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # У всех уже зарегистрированных пусто: знакомство с сайтом они тоже увидят один раз.
    op.add_column('users', sa.Column('onboarded_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'onboarded_at')
