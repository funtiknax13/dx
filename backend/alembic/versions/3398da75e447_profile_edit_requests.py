"""profile edit requests

Revision ID: 3398da75e447
Revises: e1f2a3b4c5d6
Create Date: 2026-08-21 14:07:28.490992

"""
import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3398da75e447'
down_revision: str | None = 'e1f2a3b4c5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('profile_edit_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='moderationstatus', native_enum=False, length=20), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_profile_edit_requests_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_edit_requests'))
    )
    with op.batch_alter_table('profile_edit_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_edit_requests_user_id'), ['user_id'], unique=False)

    # Backfill: every existing non-guest account gets one pending review
    # request snapshotting its current profile data — see session discussion,
    # product decision was to close community rating/stats for everyone until
    # each account gets a human look, rather than silently exempting
    # pre-existing accounts from the new moderation gate.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        """
        SELECT id, first_name, last_name, city, city_id, gender, birthday,
               phone, running_club, parent_first_name, parent_last_name, parent_phone
        FROM users
        WHERE is_guest = false
        """
    )).mappings().all()
    field_names = [
        "first_name", "last_name", "city", "city_id", "gender", "birthday",
        "phone", "running_club", "parent_first_name", "parent_last_name", "parent_phone",
    ]
    for row in rows:
        changes = {}
        for field in field_names:
            value = row[field]
            if value is None:
                continue
            changes[field] = value.isoformat() if hasattr(value, "isoformat") else value
        if not changes:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO profile_edit_requests (user_id, changes, status, created_at) "
                "VALUES (:user_id, :changes, 'pending', now())"
            ),
            {"user_id": row["id"], "changes": json.dumps(changes)},
        )


def downgrade() -> None:
    with op.batch_alter_table('profile_edit_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_edit_requests_user_id'))

    op.drop_table('profile_edit_requests')
