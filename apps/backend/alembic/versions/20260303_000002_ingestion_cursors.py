from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260303_000002'
down_revision: Union[str, None] = '20260302_000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingestion_cursors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_key', sa.String(length=120), nullable=False),
        sa.Column('cursor_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ingestion_cursors')),
        sa.UniqueConstraint('source_key', name=op.f('uq_ingestion_cursors_source_key')),
    )
    op.create_index(
        op.f('ix_ingestion_cursors_source_key'),
        'ingestion_cursors',
        ['source_key'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ingestion_cursors_source_key'), table_name='ingestion_cursors')
    op.drop_table('ingestion_cursors')
