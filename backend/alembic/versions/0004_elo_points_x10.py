"""elo: all rating points multiplied by 10

Очки переходят на шкалу Elo (старт 1000 вместо 100). Порядок и разрывы между
игроками сохраняются, история начислений и корректировок переводится в те же единицы.
Призы незавершённых турниров не трогаем: их владелец задаёт заново сам.
Призы завершённых турниров умножаем, потому что они уже вошли в очки игроков.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

SCALED_COLUMNS = {
    'users': ['rating_points'],
    'rating_changes': ['points_before', 'delta', 'points_after'],
    'rating_adjustments': ['winner_delta'],
    'rating_adjustment_log': [
        'winner_delta_before',
        'winner_delta_after',
        'winner_points_before',
        'winner_points_after',
        'loser_points_before',
        'loser_points_after',
    ],
}


def _scale(factor: str, divide: bool = False) -> None:
    op_sign = '/' if divide else '*'
    for table, columns in SCALED_COLUMNS.items():
        assignments = ', '.join(f'{column} = {column} {op_sign} {factor}' for column in columns)
        op.execute(f'UPDATE {table} SET {assignments}')
    op.execute(f"UPDATE tournaments SET win_points = win_points {op_sign} {factor} WHERE status = 'finished'")


def upgrade() -> None:
    _scale('10')
    op.alter_column('users', 'rating_points', server_default='1000', existing_type=sa.Integer(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column('users', 'rating_points', server_default='100', existing_type=sa.Integer(), existing_nullable=False)
    _scale('10', divide=True)
