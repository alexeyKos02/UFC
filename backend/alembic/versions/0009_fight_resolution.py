"""fights: admin decision on a stuck fight (accepted or cancelled)

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fights', sa.Column('resolved_by_id', sa.Integer(), nullable=True))
    op.add_column('fights', sa.Column('resolution_reason', sa.Text(), nullable=True))
    op.add_column('fights', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_fights_resolved_by_id_users'), 'fights', 'users', ['resolved_by_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_fights_resolved_by_id_users'), 'fights', type_='foreignkey')
    op.drop_column('fights', 'resolved_at')
    op.drop_column('fights', 'resolution_reason')
    op.drop_column('fights', 'resolved_by_id')
