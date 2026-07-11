"""signup event_id, one signup per event

Revision ID: b7f3a1c9e4d2
Revises: a1c3f9e2b7d4
Create Date: 2026-07-12 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f3a1c9e4d2'
down_revision: str | None = 'a1c3f9e2b7d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable at first so existing rows can be backfilled before the NOT
    # NULL + unique constraint go on.
    op.add_column('signups', sa.Column('event_id', sa.Integer(), nullable=True))
    op.execute(
        'UPDATE signups SET event_id = groups.event_id '
        'FROM groups WHERE groups.id = signups.group_id'
    )
    with op.batch_alter_table('signups', schema=None) as batch_op:
        batch_op.alter_column('event_id', nullable=False)
        batch_op.create_index(batch_op.f('ix_signups_event_id'), ['event_id'], unique=False)
        batch_op.create_foreign_key(
            batch_op.f('fk_signups_event_id_events'), 'events', ['event_id'], ['id'],
            ondelete='CASCADE',
        )
        batch_op.drop_constraint('uq_signup_runner_group', type_='unique')
        batch_op.create_unique_constraint(
            'uq_signup_runner_event', ['runner_id', 'event_id']
        )


def downgrade() -> None:
    with op.batch_alter_table('signups', schema=None) as batch_op:
        batch_op.drop_constraint('uq_signup_runner_event', type_='unique')
        batch_op.create_unique_constraint(
            'uq_signup_runner_group', ['runner_id', 'group_id']
        )
        batch_op.drop_constraint(batch_op.f('fk_signups_event_id_events'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_signups_event_id'))
        batch_op.drop_column('event_id')
