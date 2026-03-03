from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260302_000001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'event_journal',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('trace_id', sa.String(length=120), nullable=False),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column(
            'source',
            sa.Enum(
                'github',
                'agent',
                'codex',
                'policy',
                'watcher',
                name='eventsource',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'event_type',
            sa.Enum(
                'state_transition',
                'api_call',
                'comment_post',
                'execution_result',
                name='eventtype',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('ok', 'retry', 'blocked', 'error', name='eventstatus', native_enum=False),
            nullable=False,
        ),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_event_journal')),
    )
    op.create_index(op.f('ix_event_journal_entity_key'), 'event_journal', ['entity_key'], unique=False)
    op.create_index(op.f('ix_event_journal_environment'), 'event_journal', ['environment'], unique=False)
    op.create_index(op.f('ix_event_journal_job_id'), 'event_journal', ['job_id'], unique=False)
    op.create_index(op.f('ix_event_journal_timestamp'), 'event_journal', ['timestamp'], unique=False)
    op.create_index(op.f('ix_event_journal_trace_id'), 'event_journal', ['trace_id'], unique=False)

    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column(
            'kind',
            sa.Enum(
                'issue',
                'pr_author',
                'pr_reviewer',
                'review',
                'ci',
                name='jobkind',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'state',
            sa.Enum(
                'awaiting_context',
                'ready_to_execute',
                'executing',
                'awaiting_human_feedback',
                'awaiting_ci',
                'completed',
                'blocked',
                name='jobstate',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('idempotency_key', sa.String(length=120), nullable=False),
        sa.Column('lease_epoch', sa.Integer(), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'mode',
            sa.Enum('active', 'shadow', 'dry_run', name='runtimemode', native_enum=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs')),
        sa.UniqueConstraint('job_id', name=op.f('uq_jobs_job_id')),
        sa.UniqueConstraint(
            'environment',
            'idempotency_key',
            name='uq_jobs_environment_idempotency_key',
        ),
    )
    op.create_index(op.f('ix_jobs_entity_key'), 'jobs', ['entity_key'], unique=False)
    op.create_index(op.f('ix_jobs_job_id'), 'jobs', ['job_id'], unique=True)

    op.create_table(
        'job_transitions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column(
            'from_state',
            sa.Enum(
                'awaiting_context',
                'ready_to_execute',
                'executing',
                'awaiting_human_feedback',
                'awaiting_ci',
                'completed',
                'blocked',
                name='jobstate',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'to_state',
            sa.Enum(
                'awaiting_context',
                'ready_to_execute',
                'executing',
                'awaiting_human_feedback',
                'awaiting_ci',
                'completed',
                'blocked',
                name='jobstate',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('transition_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], name=op.f('fk_job_transitions_job_id_jobs')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_job_transitions')),
    )
    op.create_index(op.f('ix_job_transitions_job_id'), 'job_transitions', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_transitions_job_id'), table_name='job_transitions')
    op.drop_table('job_transitions')
    op.drop_index(op.f('ix_jobs_job_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_entity_key'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_event_journal_trace_id'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_timestamp'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_job_id'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_environment'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_entity_key'), table_name='event_journal')
    op.drop_table('event_journal')
