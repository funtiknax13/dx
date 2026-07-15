"""user privacy_accepted_at consent timestamp

Revision ID: e5f9b3d7a2c1
Revises: d2a6c8e1f4b7
Create Date: 2026-07-16 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f9b3d7a2c1'
down_revision: str | None = 'd2a6c8e1f4b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('privacy_accepted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('privacy_accepted_at')
