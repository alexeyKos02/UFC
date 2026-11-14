"""fights: admin deletes a confirmed fight (status deleted, who, when, why)

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

OLD_STATUSES = "'pending', 'disputed', 'confirmed', 'cancelled'"
NEW_STATUSES = "'pending', 'disputed', 'confirmed', 'cancelled', 'deleted'"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_fights_fight_status'), 'fights', type_='check')
    op.create_check_constraint(op.f('ck_fights_fight_status'), 'fights', f"status IN ({NEW_STATUSES})")
    op.add_column('fights', sa.Column('deleted_by_id', sa.Integer(), nullable=True))
    op.add_column('fights', sa.Column('deletion_reason', sa.Text(), nullable=True))
    op.add_column('fights', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_fights_deleted_by_id_users'), 'fights', 'users', ['deleted_by_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_fights_deleted_by_id_users'), 'fights', type_='foreignkey')
    op.drop_column('fights', 'deleted_at')
    op.drop_column('fights', 'deletion_reason')
    op.drop_column('fights', 'deleted_by_id')
    op.execute("UPDATE fights SET status = 'cancelled' WHERE status = 'deleted'")
    op.drop_constraint(op.f('ck_fights_fight_status'), 'fights', type_='check')
    op.create_check_constraint(op.f('ck_fights_fight_status'), 'fights', f"status IN ({OLD_STATUSES})")
