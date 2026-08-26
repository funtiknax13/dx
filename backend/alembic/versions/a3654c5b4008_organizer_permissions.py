"""organizer permissions

Revision ID: a3654c5b4008
Revises: 3398da75e447
Create Date: 2026-08-26 07:25:01.236597

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a3654c5b4008'
down_revision: str | None = '3398da75e447'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Note: autogenerate also picked up unrelated pre-existing drift (a stray
    # "drop running_clubs" / "drop cities trgm indexes" diff, from metadata
    # that doesn't match those tables' actual current state) — deliberately
    # excluded here, this migration only touches organizer_permissions.
    op.create_table('organizer_permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('permission', sa.Enum('csv_import', 'guest_claims', 'avatars', 'baselines', 'profile_review', 'results_review', 'surveys', name='staffpermission', native_enum=False, length=30), nullable=False),
    sa.Column('granted_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['granted_by_id'], ['users.id'], name=op.f('fk_organizer_permissions_granted_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_organizer_permissions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizer_permissions')),
    sa.UniqueConstraint('user_id', 'permission', name='uq_organizer_permissions_user_id_permission')
    )
    with op.batch_alter_table('organizer_permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organizer_permissions_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('organizer_permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organizer_permissions_user_id'))

    op.drop_table('organizer_permissions')
