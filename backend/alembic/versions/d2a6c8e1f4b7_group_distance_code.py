"""group distance_code for combined protocols

Revision ID: d2a6c8e1f4b7
Revises: c4e8f2a1b6d3
Create Date: 2026-07-13 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a6c8e1f4b7'
down_revision: str | None = 'c4e8f2a1b6d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('distance_code', sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_column('distance_code')
