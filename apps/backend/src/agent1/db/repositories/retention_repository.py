from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from sqlalchemy.orm import Session

from agent1.core.contracts import EnvironmentName
from agent1.db.models import AuditRunModel
from agent1.db.models import EventJournalModel
from agent1.db.models import GitHubEventModel

RetentionArtifactType = Literal['logs', 'traces', 'test_artifacts']


class RetentionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_purge_candidates(
        self,
        environment: EnvironmentName,
        artifact_type: RetentionArtifactType,
        cutoff_timestamp: datetime,
    ) -> int:

        '''
        Create candidate count for one retention artifact type and environment scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        artifact_type (RetentionArtifactType): Retention artifact selector.
        cutoff_timestamp (datetime): Exclusive upper timestamp bound for purge candidates.

        Returns:
        int: Candidate row count matching environment and retention cutoff.
        '''

        model_type, timestamp_column = _resolve_artifact_binding(artifact_type)
        return (
            self._session.query(model_type)
            .filter(model_type.environment == environment)
            .filter(timestamp_column < cutoff_timestamp)
            .count()
        )

    def purge_candidates(
        self,
        environment: EnvironmentName,
        artifact_type: RetentionArtifactType,
        cutoff_timestamp: datetime,
    ) -> int:

        '''
        Create purge delete-count for one retention artifact type and environment scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        artifact_type (RetentionArtifactType): Retention artifact selector.
        cutoff_timestamp (datetime): Exclusive upper timestamp bound for purge candidates.

        Returns:
        int: Deleted row count matching environment and retention cutoff.
        '''

        model_type, timestamp_column = _resolve_artifact_binding(artifact_type)
        deleted_count = (
            self._session.query(model_type)
            .filter(model_type.environment == environment)
            .filter(timestamp_column < cutoff_timestamp)
            .delete(synchronize_session=False)
        )
        return int(deleted_count)


def _resolve_artifact_binding(artifact_type: RetentionArtifactType) -> tuple[type[Any], Any]:
    if artifact_type == 'logs':
        return EventJournalModel, EventJournalModel.timestamp
    if artifact_type == 'traces':
        return GitHubEventModel, GitHubEventModel.received_at
    if artifact_type == 'test_artifacts':
        return AuditRunModel, AuditRunModel.started_at

    message = f'Unknown retention artifact type: {artifact_type}'
    raise ValueError(message)


__all__ = ['RetentionArtifactType', 'RetentionRepository']
