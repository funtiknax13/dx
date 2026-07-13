"""group counts_toward_rating flag

Revision ID: c4e8f2a1b6d3
Revises: b7f3a1c9e4d2
Create Date: 2026-07-13 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8f2a1b6d3'
down_revision: str | None = 'b7f3a1c9e4d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'counts_toward_rating', sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_column('counts_toward_rating')
