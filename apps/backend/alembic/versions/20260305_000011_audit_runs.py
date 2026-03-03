from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260305_000011'
down_revision: Union[str, None] = '20260305_000010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('audit_run_id', sa.String(length=120), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('audit_type', sa.String(length=80), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'started',
                'succeeded',
                'failed',
                name='auditrunstatus',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_runs')),
        sa.UniqueConstraint(
            'environment',
            'audit_run_id',
            name='uq_audit_runs_environment_audit_run_id',
        ),
    )
    op.create_index(op.f('ix_audit_runs_audit_run_id'), 'audit_runs', ['audit_run_id'], unique=False)
    op.create_index(op.f('ix_audit_runs_environment'), 'audit_runs', ['environment'], unique=False)
    op.create_index(op.f('ix_audit_runs_audit_type'), 'audit_runs', ['audit_type'], unique=False)
    op.create_index(op.f('ix_audit_runs_status'), 'audit_runs', ['status'], unique=False)
    op.create_index(op.f('ix_audit_runs_started_at'), 'audit_runs', ['started_at'], unique=False)
    op.create_index(op.f('ix_audit_runs_completed_at'), 'audit_runs', ['completed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_runs_completed_at'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_started_at'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_status'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_audit_type'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_environment'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_audit_run_id'), table_name='audit_runs')
    op.drop_table('audit_runs')
