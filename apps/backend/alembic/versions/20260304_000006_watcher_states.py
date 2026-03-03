from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000006'
down_revision: Union[str, None] = '20260304_000005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watcher_states',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('idle_cycles', sa.Integer(), nullable=False),
        sa.Column('watch_deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('checkpoint_cursor', sa.String(length=120), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'active',
                'reclaimed',
                'operator_required',
                'closed',
                name='watcherstatus',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('reclaim_count', sa.Integer(), nullable=False),
        sa.Column('last_reclaimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('operator_required_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], name=op.f('fk_watcher_states_job_id_jobs')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_watcher_states')),
        sa.UniqueConstraint('environment', 'job_id', name='uq_watcher_states_environment_job_id'),
    )
    op.create_index(op.f('ix_watcher_states_entity_key'), 'watcher_states', ['entity_key'], unique=False)
    op.create_index(op.f('ix_watcher_states_environment'), 'watcher_states', ['environment'], unique=False)
    op.create_index(op.f('ix_watcher_states_job_id'), 'watcher_states', ['job_id'], unique=False)
    op.create_index(
        op.f('ix_watcher_states_last_heartbeat_at'),
        'watcher_states',
        ['last_heartbeat_at'],
        unique=False,
    )
    op.create_index(op.f('ix_watcher_states_next_check_at'), 'watcher_states', ['next_check_at'], unique=False)
    op.create_index(op.f('ix_watcher_states_status'), 'watcher_states', ['status'], unique=False)
    op.create_index(
        op.f('ix_watcher_states_watch_deadline_at'),
        'watcher_states',
        ['watch_deadline_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_watcher_states_watch_deadline_at'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_status'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_next_check_at'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_last_heartbeat_at'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_job_id'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_environment'), table_name='watcher_states')
    op.drop_index(op.f('ix_watcher_states_entity_key'), table_name='watcher_states')
    op.drop_table('watcher_states')
