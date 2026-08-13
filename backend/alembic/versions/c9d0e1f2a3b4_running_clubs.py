"""running_clubs dictionary (title, city) + backfill from users.running_club

Revision ID: c9d0e1f2a3b4
Revises: b2c3d4e5f6a7
Create Date: 2026-08-13

Turns the free-text "беговой клуб" field into a picker backed by a table, while
still allowing free text (added on save). Existing distinct club names are
seeded here with an empty city.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "running_clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("search_title", sa.String(length=150), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "ix_running_clubs_search_title", "running_clubs", ["search_title"], unique=True
    )
    # Seed from clubs runners already typed (deduped by lowercased name, empty city).
    op.execute(
        """
        INSERT INTO running_clubs (title, search_title, city)
        SELECT DISTINCT ON (lower(trim(running_club)))
               trim(running_club), lower(trim(running_club)), NULL
        FROM users
        WHERE running_club IS NOT NULL AND trim(running_club) <> ''
        ORDER BY lower(trim(running_club))
        """
    )


def downgrade() -> None:
    op.drop_index("ix_running_clubs_search_title", table_name="running_clubs")
    op.drop_table("running_clubs")
