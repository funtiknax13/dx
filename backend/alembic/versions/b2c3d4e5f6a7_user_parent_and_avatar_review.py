"""users: parent contacts (<14) + avatar post-moderation state

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13

Adds guardian fields required for under-14 runners and an avatar review state.
Existing avatars are grandfathered to `approved` so the moderation queue starts
empty rather than flooded.
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_review", sa.String(length=20), nullable=False, server_default="approved"),
    )
    op.add_column("users", sa.Column("parent_first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("parent_last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("parent_phone", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "parent_phone")
    op.drop_column("users", "parent_last_name")
    op.drop_column("users", "parent_first_name")
    op.drop_column("users", "avatar_review")
