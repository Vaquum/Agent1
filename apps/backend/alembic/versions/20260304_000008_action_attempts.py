from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000008'
down_revision: Union[str, None] = '20260304_000007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('attempt_id', sa.String(length=120), nullable=False),
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
        sa.Column(
            'status',
            sa.Enum(
                'started',
                'succeeded',
                'failed',
                'aborted',
                name='actionattemptstatus',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('attempt_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempt_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['outbox_id'],
            ['outbox_entries.outbox_id'],
            name=op.f('fk_action_attempts_outbox_id_outbox_entries'),
        ),
        sa.ForeignKeyConstraint(
            ['job_id'],
            ['jobs.job_id'],
            name=op.f('fk_action_attempts_job_id_jobs'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_action_attempts')),
        sa.UniqueConstraint(
            'environment',
            'attempt_id',
            name='uq_action_attempts_environment_attempt_id',
        ),
    )
    op.create_index(op.f('ix_action_attempts_action_type'), 'action_attempts', ['action_type'], unique=False)
    op.create_index(op.f('ix_action_attempts_attempt_id'), 'action_attempts', ['attempt_id'], unique=False)
    op.create_index(
        op.f('ix_action_attempts_attempt_started_at'),
        'action_attempts',
        ['attempt_started_at'],
        unique=False,
    )
    op.create_index(op.f('ix_action_attempts_entity_key'), 'action_attempts', ['entity_key'], unique=False)
    op.create_index(op.f('ix_action_attempts_environment'), 'action_attempts', ['environment'], unique=False)
    op.create_index(op.f('ix_action_attempts_job_id'), 'action_attempts', ['job_id'], unique=False)
    op.create_index(op.f('ix_action_attempts_outbox_id'), 'action_attempts', ['outbox_id'], unique=False)
    op.create_index(op.f('ix_action_attempts_status'), 'action_attempts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_action_attempts_status'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_outbox_id'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_job_id'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_environment'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_entity_key'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_attempt_started_at'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_attempt_id'), table_name='action_attempts')
    op.drop_index(op.f('ix_action_attempts_action_type'), table_name='action_attempts')
    op.drop_table('action_attempts')
