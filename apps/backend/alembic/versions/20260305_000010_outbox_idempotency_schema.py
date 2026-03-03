from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260305_000010'
down_revision: Union[str, None] = '20260304_000009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outbox_entries',
        sa.Column('idempotency_schema_version', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'outbox_entries',
        sa.Column('idempotency_payload_hash', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'outbox_entries',
        sa.Column('idempotency_policy_version_hash', sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f('ix_outbox_entries_idempotency_schema_version'),
        'outbox_entries',
        ['idempotency_schema_version'],
        unique=False,
    )
    op.create_index(
        op.f('ix_outbox_entries_idempotency_payload_hash'),
        'outbox_entries',
        ['idempotency_payload_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_outbox_entries_idempotency_payload_hash'), table_name='outbox_entries')
    op.drop_index(op.f('ix_outbox_entries_idempotency_schema_version'), table_name='outbox_entries')
    op.drop_column('outbox_entries', 'idempotency_policy_version_hash')
    op.drop_column('outbox_entries', 'idempotency_payload_hash')
    op.drop_column('outbox_entries', 'idempotency_schema_version')
