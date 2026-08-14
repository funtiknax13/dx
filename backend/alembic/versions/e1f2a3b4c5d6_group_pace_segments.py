"""group pace_segments (structured warm-up / target / cool-down plan)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-14

Adds an optional structured pace plan to groups so a workout whose pace changes
across the run (warm-up / target / cool-down, a progression, …) can be described
as a list of segments instead of a single flat range. Display-only; the old
pace_min/pace_max columns stay as a fallback for un-migrated groups.
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("pace_segments", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "pace_segments")
