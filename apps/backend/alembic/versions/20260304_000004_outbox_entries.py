from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000004'
down_revision: Union[str, None] = '20260303_000003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('outbox_id', sa.String(length=120), nullable=False),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'action_type',
            sa.Enum('issue_comment', 'pr_review_reply', name='outboxactiontype', native_enum=False),
            nullable=False,
        ),
        sa.Column('target_identity', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=120), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'pending',
                'sent',
                'confirmed',
                'failed',
                'aborted',
                name='outboxstatus',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('lease_epoch', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id']),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_entries')),
        sa.UniqueConstraint(
            'environment',
            'action_type',
            'target_identity',
            'idempotency_key',
            name='uq_outbox_environment_action_target_idempotency',
        ),
        sa.UniqueConstraint('outbox_id', name=op.f('uq_outbox_entries_outbox_id')),
    )
    op.create_index(op.f('ix_outbox_entries_action_type'), 'outbox_entries', ['action_type'], unique=False)
    op.create_index(op.f('ix_outbox_entries_entity_key'), 'outbox_entries', ['entity_key'], unique=False)
    op.create_index(op.f('ix_outbox_entries_environment'), 'outbox_entries', ['environment'], unique=False)
    op.create_index(op.f('ix_outbox_entries_idempotency_key'), 'outbox_entries', ['idempotency_key'], unique=False)
    op.create_index(op.f('ix_outbox_entries_job_id'), 'outbox_entries', ['job_id'], unique=False)
    op.create_index(op.f('ix_outbox_entries_next_attempt_at'), 'outbox_entries', ['next_attempt_at'], unique=False)
    op.create_index(op.f('ix_outbox_entries_outbox_id'), 'outbox_entries', ['outbox_id'], unique=True)
    op.create_index(op.f('ix_outbox_entries_status'), 'outbox_entries', ['status'], unique=False)
    op.create_index(op.f('ix_outbox_entries_target_identity'), 'outbox_entries', ['target_identity'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_outbox_entries_target_identity'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_status'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_outbox_id'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_next_attempt_at'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_job_id'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_idempotency_key'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_environment'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_entity_key'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_action_type'), table_name='outbox_entries')
    op.drop_table('outbox_entries')
