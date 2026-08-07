"""Drop the "other" gender option; null out any existing rows that used it

Revision ID: b1a2c3d4e5f6
Revises: 426f92b1546d
Create Date: 2026-08-07

The Gender enum is stored as a plain VARCHAR (native_enum=False), so there's
no DB enum type to alter — only existing data to clean up: anyone who had
picked "other" is set back to NULL (unspecified), since the app no longer
offers that value.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b1a2c3d4e5f6"
down_revision: str | Sequence[str] | None = "426f92b1546d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET gender = NULL WHERE gender = 'other'")


def downgrade() -> None:
    # Irreversible: which NULLs were previously "other" isn't recorded.
    pass
