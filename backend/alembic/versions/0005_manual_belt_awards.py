"""manual belt awards: admin gives a belt without a fight

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

OLD_SINGLE_SOURCE = '(tournament_id IS NULL) <> (title_fight_id IS NULL)'
NEW_SINGLE_SOURCE = (
    '(tournament_id IS NOT NULL)::int + (title_fight_id IS NOT NULL)::int + (awarded_by_id IS NOT NULL)::int = 1'
)


def upgrade() -> None:
    op.add_column('belt_wins', sa.Column('awarded_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('fk_belt_wins_awarded_by_id_users'), 'belt_wins', 'users', ['awarded_by_id'], ['id']
    )
    op.alter_column('belt_wins', 'fight_id', existing_type=sa.Integer(), nullable=True)
    op.drop_constraint(op.f('ck_belt_wins_single_source'), 'belt_wins', type_='check')
    op.create_check_constraint(op.f('ck_belt_wins_single_source'), 'belt_wins', NEW_SINGLE_SOURCE)
    op.create_check_constraint(
        op.f('ck_belt_wins_fight_unless_manual'), 'belt_wins', '(fight_id IS NULL) = (awarded_by_id IS NOT NULL)'
    )


def downgrade() -> None:
    # Выданные без боя пояса в старой схеме не выразить: такие записи удаляются,
    # а у поясов, где они были последними, остаётся тот же чемпион.
    op.execute('DELETE FROM belt_wins WHERE awarded_by_id IS NOT NULL')
    op.drop_constraint(op.f('ck_belt_wins_fight_unless_manual'), 'belt_wins', type_='check')
    op.drop_constraint(op.f('ck_belt_wins_single_source'), 'belt_wins', type_='check')
    op.create_check_constraint(op.f('ck_belt_wins_single_source'), 'belt_wins', OLD_SINGLE_SOURCE)
    op.alter_column('belt_wins', 'fight_id', existing_type=sa.Integer(), nullable=False)
    op.drop_constraint(op.f('fk_belt_wins_awarded_by_id_users'), 'belt_wins', type_='foreignkey')
    op.drop_column('belt_wins', 'awarded_by_id')
