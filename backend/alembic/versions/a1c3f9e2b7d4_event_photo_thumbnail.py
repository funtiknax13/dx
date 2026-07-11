"""event photo thumbnail

Revision ID: a1c3f9e2b7d4
Revises: 9359b13eb026
Create Date: 2026-07-11 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3f9e2b7d4'
down_revision: str | None = '9359b13eb026'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('event_photos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thumbnail', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('event_photos', schema=None) as batch_op:
        batch_op.drop_column('thumbnail')
