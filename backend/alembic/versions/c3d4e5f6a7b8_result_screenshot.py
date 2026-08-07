"""Add screenshot column to results

Revision ID: c3d4e5f6a7b8
Revises: b1a2c3d4e5f6
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b1a2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("results", sa.Column("screenshot", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "screenshot")
