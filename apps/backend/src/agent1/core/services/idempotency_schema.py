from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from agent1.core.contracts import OutboxActionType

IDEMPOTENCY_SCHEMA_PREFIX = 'idem'
IDEMPOTENCY_SCHEMA_VERSION = 'v1'
IDEMPOTENCY_COMPONENT_SEPARATOR = '|'
IDEMPOTENCY_DEFAULT_POLICY_VERSION = 'unversioned'


@dataclass(frozen=True)
class CanonicalIdempotencyScope:
    idempotency_key: str
    schema_version: str
    payload_hash: str
    policy_version_hash: str


def _normalize_component(component: str, component_name: str) -> str:

    '''
    Create normalized idempotency-key component with empty-value rejection.

    Args:
    component (str): Raw idempotency component value.
    component_name (str): Deterministic component field name.

    Returns:
    str: Trimmed idempotency component value.
    '''

    normalized_component = component.strip()
    if normalized_component == '':
        message = f'Idempotency schema requires non-empty component: {component_name}'
        raise ValueError(message)

    return normalized_component


def _create_payload_hash(payload: dict[str, object]) -> str:

    '''
    Create stable payload hash for deterministic idempotency schema composition.

    Args:
    payload (dict[str, object]): Outbox payload for side-effect intent.

    Returns:
    str: SHA256 hash of normalized payload.
    '''

    normalized_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(normalized_payload.encode('utf-8')).hexdigest()


def _create_policy_version_hash(policy_version: str) -> str:

    '''
    Create stable policy-version hash for deterministic idempotency schema composition.

    Args:
    policy_version (str): Policy version string used for decision context.

    Returns:
    str: SHA256 hash of normalized policy version.
    '''

    normalized_policy_version = _normalize_component(policy_version, 'policy_version')
    return hashlib.sha256(normalized_policy_version.encode('utf-8')).hexdigest()


def build_canonical_idempotency_key(
    entity_key: str,
    action_type: OutboxActionType,
    target_identity: str,
    payload: dict[str, object] | None = None,
    policy_version: str = IDEMPOTENCY_DEFAULT_POLICY_VERSION,
) -> str:

    '''
    Create canonical idempotency key from deterministic side-effect scope fields.

    Args:
    entity_key (str): Durable entity key.
    action_type (OutboxActionType): Outbox side-effect action type.
    target_identity (str): Deterministic side-effect target identity.
    payload (dict[str, object] | None): Optional side-effect payload for hash composition.
    policy_version (str): Policy version string for hash composition.

    Returns:
    str: Canonical idempotency key string.
    '''

    canonical_scope = build_canonical_idempotency_scope(
        entity_key=entity_key,
        action_type=action_type,
        target_identity=target_identity,
        payload=payload,
        policy_version=policy_version,
    )
    return canonical_scope.idempotency_key


def build_canonical_idempotency_scope(
    entity_key: str,
    action_type: OutboxActionType,
    target_identity: str,
    payload: dict[str, object] | None = None,
    policy_version: str = IDEMPOTENCY_DEFAULT_POLICY_VERSION,
) -> CanonicalIdempotencyScope:

    '''
    Create canonical idempotency schema components from deterministic side-effect scope.

    Args:
    entity_key (str): Durable entity key.
    action_type (OutboxActionType): Outbox side-effect action type.
    target_identity (str): Deterministic side-effect target identity.
    payload (dict[str, object] | None): Optional side-effect payload for hash composition.
    policy_version (str): Policy version string for hash composition.

    Returns:
    CanonicalIdempotencyScope: Canonical idempotency schema components.
    '''

    normalized_entity_key = _normalize_component(entity_key, 'entity_key')
    normalized_target_identity = _normalize_component(target_identity, 'target_identity')
    normalized_payload = payload or {}
    payload_hash = _create_payload_hash(normalized_payload)
    policy_version_hash = _create_policy_version_hash(policy_version)
    canonical_payload = IDEMPOTENCY_COMPONENT_SEPARATOR.join(
        [
            f'schema={IDEMPOTENCY_SCHEMA_VERSION}',
            f'entity_key={normalized_entity_key}',
            f'action_type={action_type.value}',
            f'target_identity={normalized_target_identity}',
            f'payload_hash={payload_hash}',
            f'policy_version_hash={policy_version_hash}',
        ],
    )
    canonical_hash = hashlib.sha256(canonical_payload.encode('utf-8')).hexdigest()
    return CanonicalIdempotencyScope(
        idempotency_key=f'{IDEMPOTENCY_SCHEMA_PREFIX}:{IDEMPOTENCY_SCHEMA_VERSION}:{canonical_hash}',
        schema_version=IDEMPOTENCY_SCHEMA_VERSION,
        payload_hash=payload_hash,
        policy_version_hash=policy_version_hash,
    )


__all__ = [
    'CanonicalIdempotencyScope',
    'IDEMPOTENCY_DEFAULT_POLICY_VERSION',
    'build_canonical_idempotency_key',
    'build_canonical_idempotency_scope',
]
