"""result comment (runner's note explaining a mismatch with the group)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-14

Optional free-text field a runner can fill in when their run doesn't match the
group (GPS dropped, ran to the start from home, etc.), shown to the moderator.
"""

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("results", sa.Column("comment", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "comment")
