"""Result.screenshot (single) -> screenshots (JSON list)

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-08-11

A manual result can now carry several screenshots (e.g. one showing the date,
another the route) instead of a single one. Existing single screenshots are
folded into a one-element list.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("results", sa.Column("screenshots", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE results SET screenshots = json_build_array(screenshot) "
        "WHERE screenshot IS NOT NULL"
    )
    op.drop_column("results", "screenshot")


def downgrade() -> None:
    op.add_column("results", sa.Column("screenshot", sa.String(length=500), nullable=True))
    # Keep only the first screenshot on the way back down.
    op.execute("UPDATE results SET screenshot = screenshots->>0 WHERE screenshots IS NOT NULL")
    op.drop_column("results", "screenshots")
