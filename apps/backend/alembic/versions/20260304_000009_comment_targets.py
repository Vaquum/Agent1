from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000009'
down_revision: Union[str, None] = '20260304_000008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comment_targets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('target_id', sa.String(length=120), nullable=False),
        sa.Column('outbox_id', sa.String(length=120), nullable=False),
        sa.Column('job_id', sa.String(length=120), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'target_type',
            sa.Enum(
                'issue',
                'pr',
                'pr_review_thread',
                name='commenttargettype',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('target_identity', sa.String(length=255), nullable=False),
        sa.Column('issue_number', sa.Integer(), nullable=True),
        sa.Column('pr_number', sa.Integer(), nullable=True),
        sa.Column('thread_id', sa.String(length=120), nullable=True),
        sa.Column('review_comment_id', sa.Integer(), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('line', sa.Integer(), nullable=True),
        sa.Column('side', sa.String(length=20), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['outbox_id'],
            ['outbox_entries.outbox_id'],
            name=op.f('fk_comment_targets_outbox_id_outbox_entries'),
        ),
        sa.ForeignKeyConstraint(
            ['job_id'],
            ['jobs.job_id'],
            name=op.f('fk_comment_targets_job_id_jobs'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_comment_targets')),
        sa.UniqueConstraint('target_id', name=op.f('uq_comment_targets_target_id')),
        sa.UniqueConstraint(
            'environment',
            'outbox_id',
            name='uq_comment_targets_environment_outbox_id',
        ),
    )
    op.create_index(op.f('ix_comment_targets_entity_key'), 'comment_targets', ['entity_key'], unique=False)
    op.create_index(op.f('ix_comment_targets_environment'), 'comment_targets', ['environment'], unique=False)
    op.create_index(op.f('ix_comment_targets_job_id'), 'comment_targets', ['job_id'], unique=False)
    op.create_index(op.f('ix_comment_targets_outbox_id'), 'comment_targets', ['outbox_id'], unique=False)
    op.create_index(op.f('ix_comment_targets_resolved_at'), 'comment_targets', ['resolved_at'], unique=False)
    op.create_index(op.f('ix_comment_targets_target_id'), 'comment_targets', ['target_id'], unique=False)
    op.create_index(op.f('ix_comment_targets_target_identity'), 'comment_targets', ['target_identity'], unique=False)
    op.create_index(op.f('ix_comment_targets_target_type'), 'comment_targets', ['target_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_comment_targets_target_type'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_target_identity'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_target_id'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_resolved_at'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_outbox_id'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_job_id'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_environment'), table_name='comment_targets')
    op.drop_index(op.f('ix_comment_targets_entity_key'), table_name='comment_targets')
    op.drop_table('comment_targets')
