"""contest multi select and multi entries

Revision ID: 741e268b34b6
Revises: e866562b7b0b
Create Date: 2026-10-24 11:02:09.942541

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "741e268b34b6"
down_revision: str | None = "e866562b7b0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed dropping cities' GIN trigram indexes — a
    # known false positive (autogenerate doesn't see postgresql_ops-based
    # indexes correctly), stripped here same as every prior migration.
    with op.batch_alter_table("contest_entries", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_contest_entry_runner"), type_="unique")

    with op.batch_alter_table("contest_fields", schema=None) as batch_op:
        batch_op.add_column(sa.Column("options", sa.JSON(), nullable=True))

    with op.batch_alter_table("contests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("max_entries_per_runner", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contests", schema=None) as batch_op:
        batch_op.drop_column("max_entries_per_runner")

    with op.batch_alter_table("contest_fields", schema=None) as batch_op:
        batch_op.drop_column("options")

    with op.batch_alter_table("contest_entries", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            batch_op.f("uq_contest_entry_runner"),
            ["contest_id", "runner_id"],
            postgresql_nulls_not_distinct=False,
        )
