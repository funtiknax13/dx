"""backfill events and support permissions

Revision ID: 7eb7d3698bc5
Revises: a3654c5b4008
Create Date: 2026-08-26 08:22:52.455041

Data-only — no schema change. `events` and `support` join StaffPermission
as two more delegable capabilities, but until now they were an
*unconditional* organizer baseline (every organizer could always create
events/groups and handle support tickets). Every existing organizer gets
both grants here so this migration doesn't silently lock any of them out;
a *newly promoted* organizer from here on starts with nothing (see
admin.tools_permissions.promote_to_organizer) — same secure-default as
every other permission in this system.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7eb7d3698bc5"
down_revision: str | None = "a3654c5b4008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    for permission in ("events", "support"):
        conn.execute(
            sa.text(
                """
                INSERT INTO organizer_permissions (user_id, permission, created_at)
                SELECT id, :permission, now() FROM users WHERE role = 'organizer'
                ON CONFLICT (user_id, permission) DO NOTHING
                """
            ),
            {"permission": permission},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM organizer_permissions WHERE permission IN ('events', 'support')")
    )
