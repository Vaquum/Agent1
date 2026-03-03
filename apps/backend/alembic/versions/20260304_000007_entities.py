from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260304_000007'
down_revision: Union[str, None] = '20260304_000006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False),
        sa.Column('repository', sa.String(length=255), nullable=False),
        sa.Column('entity_number', sa.Integer(), nullable=False),
        sa.Column(
            'entity_type',
            sa.Enum('issue', 'pr', name='entitytype', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'environment',
            sa.Enum('dev', 'prod', 'ci', name='environmentname', native_enum=False),
            nullable=False,
        ),
        sa.Column('is_sandbox', sa.Boolean(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), nullable=False),
        sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_entities')),
        sa.UniqueConstraint(
            'environment',
            'entity_key',
            name='uq_entities_environment_entity_key',
        ),
    )
    op.create_index(op.f('ix_entities_entity_key'), 'entities', ['entity_key'], unique=False)
    op.create_index(op.f('ix_entities_entity_number'), 'entities', ['entity_number'], unique=False)
    op.create_index(op.f('ix_entities_entity_type'), 'entities', ['entity_type'], unique=False)
    op.create_index(op.f('ix_entities_environment'), 'entities', ['environment'], unique=False)
    op.create_index(op.f('ix_entities_last_event_at'), 'entities', ['last_event_at'], unique=False)
    op.create_index(op.f('ix_entities_repository'), 'entities', ['repository'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_entities_repository'), table_name='entities')
    op.drop_index(op.f('ix_entities_last_event_at'), table_name='entities')
    op.drop_index(op.f('ix_entities_environment'), table_name='entities')
    op.drop_index(op.f('ix_entities_entity_type'), table_name='entities')
    op.drop_index(op.f('ix_entities_entity_number'), table_name='entities')
    op.drop_index(op.f('ix_entities_entity_key'), table_name='entities')
    op.drop_table('entities')
