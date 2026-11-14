"""points by fight date: recalculation marks and full replay of history

Очки теперь считаются по дате боя, а не по порядку подтверждения. Бой, сыгранный раньше уже
подтверждённых, пересчитывает следующие; у пересчитанных боёв ставится пометка.
Миграция один раз проигрывает всю историю заново в порядке дат боёв.

Пересчёт вызывает app/services/recalc.py: он работает на обычном SQL без ORM-моделей.
Если когда-нибудь поменяются таблицы, которые он читает, сюда нужно положить замороженную копию.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa



revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fights', sa.Column('points_recalculated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fights', sa.Column('recalculated_by_fight_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('fk_fights_recalculated_by_fight_id_fights'), 'fights', 'fights', ['recalculated_by_fight_id'], ['id']
    )
    # Полный пересчёт истории здесь был нужен при переходе на очки по дате боя. Теперь его
    # делает 0012 (турнирные бои без Elo): текущий recalc читает колонки, которых в 0010 ещё нет.


def downgrade() -> None:
    # Очки остаются пересчитанными по дате боя: прежний порядок восстанавливается только из бэкапа.
    op.drop_constraint(op.f('fk_fights_recalculated_by_fight_id_fights'), 'fights', type_='foreignkey')
    op.drop_column('fights', 'recalculated_by_fight_id')
    op.drop_column('fights', 'points_recalculated_at')
