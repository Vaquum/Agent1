from __future__ import annotations

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260303_000003'
down_revision: Union[str, None] = '20260303_000002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'runtime_scope_guards'
    if not inspector.has_table(table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('scope_key', sa.String(length=255), nullable=False),
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
            sa.Column('instance_id', sa.String(length=120), nullable=False),
            sa.Column('stale_after_seconds', sa.Integer(), nullable=False),
            sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_runtime_scope_guards')),
            sa.UniqueConstraint('scope_key', name=op.f('uq_runtime_scope_guards_scope_key')),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {
        index['name'] for index in inspector.get_indexes(table_name)
    }
    environment_index = op.f('ix_runtime_scope_guards_environment')
    if environment_index not in existing_indexes:
        op.create_index(
            environment_index,
            table_name,
            ['environment'],
            unique=False,
        )

    scope_key_index = op.f('ix_runtime_scope_guards_scope_key')
    if scope_key_index not in existing_indexes:
        op.create_index(
            scope_key_index,
            table_name,
            ['scope_key'],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_runtime_scope_guards_scope_key'), table_name='runtime_scope_guards')
    op.drop_index(op.f('ix_runtime_scope_guards_environment'), table_name='runtime_scope_guards')
    op.drop_table('runtime_scope_guards')
