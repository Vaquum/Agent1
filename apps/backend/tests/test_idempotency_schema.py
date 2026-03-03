from __future__ import annotations

import pytest

from agent1.core.contracts import OutboxActionType
from agent1.core.services.idempotency_schema import build_canonical_idempotency_key
from agent1.core.services.idempotency_schema import build_canonical_idempotency_scope


def test_build_canonical_idempotency_key_is_deterministic() -> None:
    first = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#77',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:77',
        payload={'repository': 'Vaquum/Agent1', 'issue_number': 77, 'body': 'hello'},
        policy_version='0.1.0',
    )
    second = build_canonical_idempotency_key(
        entity_key='  Vaquum/Agent1#77  ',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='  Vaquum/Agent1:issue:77  ',
        payload={'body': 'hello', 'issue_number': 77, 'repository': 'Vaquum/Agent1'},
        policy_version='0.1.0',
    )

    assert first == second
    assert first.startswith('idem:v1:')


def test_build_canonical_idempotency_key_changes_with_scope() -> None:
    issue_comment_key = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#78',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:78',
    )
    review_reply_key = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#78',
        action_type=OutboxActionType.PR_REVIEW_REPLY,
        target_identity='Vaquum/Agent1:pr:78:thread:PRRC_78:9078',
    )

    assert issue_comment_key != review_reply_key


def test_build_canonical_idempotency_key_changes_with_payload_hash() -> None:
    baseline = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#80',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:80',
        payload={'body': 'first'},
        policy_version='0.1.0',
    )
    changed_payload = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#80',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:80',
        payload={'body': 'second'},
        policy_version='0.1.0',
    )

    assert baseline != changed_payload


def test_build_canonical_idempotency_key_changes_with_policy_version_hash() -> None:
    baseline = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#81',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:81',
        payload={'body': 'stable'},
        policy_version='0.1.0',
    )
    changed_policy_version = build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#81',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:81',
        payload={'body': 'stable'},
        policy_version='0.2.0',
    )

    assert baseline != changed_policy_version


def test_build_canonical_idempotency_key_rejects_empty_components() -> None:
    with pytest.raises(ValueError):
        build_canonical_idempotency_key(
            entity_key='',
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1:issue:79',
        )

    with pytest.raises(ValueError):
        build_canonical_idempotency_key(
            entity_key='Vaquum/Agent1#79',
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity=' ',
        )


def test_build_canonical_idempotency_scope_returns_schema_components() -> None:
    scope = build_canonical_idempotency_scope(
        entity_key='Vaquum/Agent1#82',
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1:issue:82',
        payload={'body': 'hello'},
        policy_version='0.3.0',
    )

    assert scope.schema_version == 'v1'
    assert len(scope.payload_hash) == 64
    assert len(scope.policy_version_hash) == 64
    assert scope.idempotency_key.startswith('idem:v1:')
