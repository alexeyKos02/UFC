"""points for non-main belts won in a fight

belts.title_points — очки лиги за неосновной пояс, взятый в бою за пояс (не в турнире):
взял +N, чемпион, проигравший пояс, −N, защита +N/2. title_fights.belt_points запоминает сумму
при подтверждении боя, rating_changes.belt_delta — сколько начислено за пояс в этом бою.
У существующих поясов сумма 0, поэтому история не меняется.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('belts', sa.Column('title_points', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_belts_title_points_non_negative'), 'belts', 'title_points >= 0')
    op.add_column('title_fights', sa.Column('belt_points', sa.Integer(), nullable=True))
    op.add_column('rating_changes', sa.Column('belt_delta', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('rating_changes', 'belt_delta')
    op.drop_column('title_fights', 'belt_points')
    op.drop_constraint(op.f('ck_belts_title_points_non_negative'), 'belts', type_='check')
    op.drop_column('belts', 'title_points')
