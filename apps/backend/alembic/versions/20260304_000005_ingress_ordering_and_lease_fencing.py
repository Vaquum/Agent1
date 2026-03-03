from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000005'
down_revision: Union[str, None] = '20260304_000004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outbox_entries',
        sa.Column('job_lease_epoch', sa.Integer(), nullable=False, server_default='0'),
    )

    op.create_table(
        'ingress_entity_cursors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column('high_water_source_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('high_water_source_event_id', sa.String(length=120), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ingress_entity_cursors')),
        sa.UniqueConstraint(
            'environment',
            'entity_key',
            name='uq_ingress_entity_cursors_environment_entity_key',
        ),
    )
    op.create_index(
        op.f('ix_ingress_entity_cursors_environment'),
        'ingress_entity_cursors',
        ['environment'],
        unique=False,
    )
    op.create_index(
        op.f('ix_ingress_entity_cursors_entity_key'),
        'ingress_entity_cursors',
        ['entity_key'],
        unique=False,
    )

    op.create_table(
        'github_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_event_id', sa.String(length=120), nullable=False),
        sa.Column('source_timestamp_or_seq', sa.String(length=120), nullable=False),
        sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('repository', sa.String(length=255), nullable=False),
        sa.Column('entity_number', sa.Integer(), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column('actor', sa.String(length=120), nullable=False),
        sa.Column('ingress_event_type', sa.String(length=80), nullable=False),
        sa.Column('ordering_decision', sa.String(length=20), nullable=False),
        sa.Column('is_stale', sa.Boolean(), nullable=False),
        sa.Column('stale_reason', sa.String(length=255), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_github_events')),
    )
    op.create_index(op.f('ix_github_events_actor'), 'github_events', ['actor'], unique=False)
    op.create_index(op.f('ix_github_events_entity_key'), 'github_events', ['entity_key'], unique=False)
    op.create_index(op.f('ix_github_events_entity_number'), 'github_events', ['entity_number'], unique=False)
    op.create_index(op.f('ix_github_events_environment'), 'github_events', ['environment'], unique=False)
    op.create_index(
        op.f('ix_github_events_ingress_event_type'),
        'github_events',
        ['ingress_event_type'],
        unique=False,
    )
    op.create_index(op.f('ix_github_events_is_stale'), 'github_events', ['is_stale'], unique=False)
    op.create_index(
        op.f('ix_github_events_ordering_decision'),
        'github_events',
        ['ordering_decision'],
        unique=False,
    )
    op.create_index(op.f('ix_github_events_received_at'), 'github_events', ['received_at'], unique=False)
    op.create_index(op.f('ix_github_events_repository'), 'github_events', ['repository'], unique=False)
    op.create_index(op.f('ix_github_events_source_event_id'), 'github_events', ['source_event_id'], unique=False)
    op.create_index(
        op.f('ix_github_events_source_timestamp'),
        'github_events',
        ['source_timestamp'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_github_events_source_timestamp'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_source_event_id'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_repository'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_received_at'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_ordering_decision'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_is_stale'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_ingress_event_type'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_environment'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_entity_number'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_entity_key'), table_name='github_events')
    op.drop_index(op.f('ix_github_events_actor'), table_name='github_events')
    op.drop_table('github_events')

    op.drop_index(op.f('ix_ingress_entity_cursors_entity_key'), table_name='ingress_entity_cursors')
    op.drop_index(op.f('ix_ingress_entity_cursors_environment'), table_name='ingress_entity_cursors')
    op.drop_table('ingress_entity_cursors')

    op.drop_column('outbox_entries', 'job_lease_epoch')
