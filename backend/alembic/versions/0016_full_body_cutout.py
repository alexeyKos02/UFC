"""full-body photos with a transparent background

users.full_body_cutout — фото в полный рост с прозрачным фоном: на сайте без рамки и крупнее.
Уже загруженные фото проверяются по файлу (по краям картинки прозрачно — значит, фигура вырезана).

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

from app.services import uploads


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_body_cutout', sa.Boolean(), server_default='false', nullable=False))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, full_body_path FROM users WHERE full_body_path IS NOT NULL")).all()
    cutouts = [row.id for row in rows if uploads.stored_is_cutout(row.full_body_path)]
    if cutouts:
        connection.execute(
            sa.text("UPDATE users SET full_body_cutout = true WHERE id = ANY(:ids)"), {"ids": cutouts}
        )


def downgrade() -> None:
    op.drop_column('users', 'full_body_cutout')
