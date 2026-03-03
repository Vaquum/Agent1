from __future__ import annotations

from datetime import datetime
from datetime import timezone
import hashlib
import json
from typing import Any
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260306_000012'
down_revision: Union[str, None] = '20260305_000011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _to_canonical_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            normalized_value = value.replace(tzinfo=timezone.utc)
        else:
            normalized_value = value.astimezone(timezone.utc)
        return normalized_value.isoformat()

    if isinstance(value, str):
        normalized_input = value.replace('Z', '+00:00')
        try:
            parsed_value = datetime.fromisoformat(normalized_input)
        except ValueError:
            return value

        if parsed_value.tzinfo is None:
            parsed_value = parsed_value.replace(tzinfo=timezone.utc)
        else:
            parsed_value = parsed_value.astimezone(timezone.utc)
        return parsed_value.isoformat()

    return str(value)


def _to_canonical_payload_value(value: object) -> Any:
    if isinstance(value, datetime):
        return _to_canonical_timestamp(value)
    if isinstance(value, dict):
        return {
            str(key): _to_canonical_payload_value(payload_value)
            for key, payload_value in value.items()
        }
    if isinstance(value, list):
        return [_to_canonical_payload_value(payload_value) for payload_value in value]

    return value


def _to_canonical_details(value: object) -> object:
    if value is None:
        return {}

    if isinstance(value, str):
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            return value
        return _to_canonical_payload_value(parsed_value)

    return _to_canonical_payload_value(value)


def _compute_payload_hash(
    row: dict[str, object],
    event_seq: int,
    prev_event_hash: str | None,
) -> str:
    payload = {
        'timestamp': _to_canonical_timestamp(row['timestamp']),
        'environment': str(row['environment']),
        'trace_id': str(row['trace_id']),
        'job_id': str(row['job_id']),
        'entity_key': str(row['entity_key']),
        'source': str(row['source']),
        'event_type': str(row['event_type']),
        'status': str(row['status']),
        'details': _to_canonical_details(row['details']),
        'event_seq': event_seq,
        'prev_event_hash': prev_event_hash,
    }
    serialized_payload = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(serialized_payload.encode('utf-8')).hexdigest()


def _backfill_event_chain() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            '''
            SELECT
                id,
                timestamp,
                environment,
                trace_id,
                job_id,
                entity_key,
                source,
                event_type,
                status,
                details
            FROM event_journal
            ORDER BY environment ASC, timestamp ASC, id ASC
            '''
        )
    ).mappings().all()
    chain_state_by_environment: dict[str, tuple[int, str | None]] = {}
    for row in rows:
        row_payload = dict(row)
        environment_value = str(row_payload['environment'])
        chain_state = chain_state_by_environment.get(environment_value, (0, None))
        event_seq = chain_state[0] + 1
        prev_event_hash = chain_state[1]
        payload_hash = _compute_payload_hash(
            row=row_payload,
            event_seq=event_seq,
            prev_event_hash=prev_event_hash,
        )
        connection.execute(
            sa.text(
                '''
                UPDATE event_journal
                SET event_seq = :event_seq,
                    prev_event_hash = :prev_event_hash,
                    payload_hash = :payload_hash
                WHERE id = :event_id
                '''
            ),
            {
                'event_seq': event_seq,
                'prev_event_hash': prev_event_hash,
                'payload_hash': payload_hash,
                'event_id': row_payload['id'],
            },
        )
        chain_state_by_environment[environment_value] = (event_seq, payload_hash)


def upgrade() -> None:
    op.add_column(
        'event_journal',
        sa.Column('event_seq', sa.Integer(), nullable=True),
    )
    op.add_column(
        'event_journal',
        sa.Column('prev_event_hash', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'event_journal',
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
    )
    op.create_index(op.f('ix_event_journal_event_seq'), 'event_journal', ['event_seq'], unique=False)
    op.create_index(
        op.f('ix_event_journal_prev_event_hash'),
        'event_journal',
        ['prev_event_hash'],
        unique=False,
    )
    op.create_index(
        op.f('ix_event_journal_payload_hash'),
        'event_journal',
        ['payload_hash'],
        unique=False,
    )
    _backfill_event_chain()
    op.create_index(
        'uq_event_journal_environment_event_seq',
        'event_journal',
        ['environment', 'event_seq'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_event_journal_environment_event_seq', table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_payload_hash'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_prev_event_hash'), table_name='event_journal')
    op.drop_index(op.f('ix_event_journal_event_seq'), table_name='event_journal')
    op.drop_column('event_journal', 'payload_hash')
    op.drop_column('event_journal', 'prev_event_hash')
    op.drop_column('event_journal', 'event_seq')
