"""tournaments: fights give no league Elo, prizes for 1st-3rd place, optional 3rd-place match

Бои турнира больше не меняют очки лиги: их начисления удаляются, ручные корректировки на них
отменяются, история пересчитывается целиком (app/services/recalc.py). Призы в очки лиги:
win_points (1-е место), second_points, third_points. У уже идущих и завершённых турниров
матча за 3-е место нет, призы за 2-е и 3-е места — 0.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

from app.services import recalc


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tournaments', sa.Column('second_points', sa.Integer(), server_default='0', nullable=False))
    op.add_column('tournaments', sa.Column('third_points', sa.Integer(), server_default='0', nullable=False))
    op.add_column('tournaments', sa.Column('has_third_place', sa.Boolean(), server_default='false', nullable=False))
    op.create_check_constraint(op.f('ck_tournaments_second_points_non_negative'), 'tournaments', 'second_points >= 0')
    op.create_check_constraint(op.f('ck_tournaments_third_points_non_negative'), 'tournaments', 'third_points >= 0')
    op.add_column(
        'tournament_matches', sa.Column('is_third_place', sa.Boolean(), server_default='false', nullable=False)
    )

    op.execute(
        "DELETE FROM rating_changes WHERE fight_id IN (SELECT id FROM fights WHERE kind = 'tournament')"
    )
    op.execute(
        "UPDATE rating_adjustments SET status = 'cancelled' WHERE status = 'active' "
        "AND fight_id IN (SELECT id FROM fights WHERE kind = 'tournament')"
    )
    recalc.recalculate(op.get_bind())


def downgrade() -> None:
    op.drop_column('tournament_matches', 'is_third_place')
    op.drop_constraint(op.f('ck_tournaments_third_points_non_negative'), 'tournaments', type_='check')
    op.drop_constraint(op.f('ck_tournaments_second_points_non_negative'), 'tournaments', type_='check')
    op.drop_column('tournaments', 'has_third_place')
    op.drop_column('tournaments', 'third_points')
    op.drop_column('tournaments', 'second_points')
