from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from enum import Enum
import json

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.control_schemas import RetentionPolicyControl
from agent1.db.repositories.event_repository import EventRepository
from agent1.db.repositories.retention_repository import RetentionArtifactType
from agent1.db.repositories.retention_repository import RetentionRepository
from agent1.db.session import create_session_factory

RETENTION_ARTIFACT_ORDER: tuple[RetentionArtifactType, ...] = (
    'logs',
    'traces',
    'test_artifacts',
)


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for retention purge operations.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class RetentionPurgeMode(str, Enum):
    DRY_RUN = 'dry_run'
    EXECUTE = 'execute'


class RetentionPurgeArtifactReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    artifact_type: RetentionArtifactType
    retention_days: int = Field(gt=0)
    cutoff_timestamp: datetime
    candidate_count: int = Field(ge=0)
    purged_count: int = Field(ge=0)
    post_purge_rebuild_rows: int = Field(ge=0, default=0)


class RetentionPurgeReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    environment: EnvironmentName
    mode: RetentionPurgeMode
    reference_timestamp: datetime
    executed_at: datetime
    artifact_reports: list[RetentionPurgeArtifactReport] = Field(default_factory=list)
    total_candidates: int = Field(ge=0)
    total_purged: int = Field(ge=0)


class RetentionPurgeService:
    def __init__(
        self,
        retention_policy: RetentionPolicyControl,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or create_session_factory()
        self._retention_days_by_scope = {
            (entry.artifact_type, entry.environment): entry.retention_days
            for entry in retention_policy.entries
        }
        self._validate_scope_coverage()

    def run(
        self,
        environment: EnvironmentName,
        mode: RetentionPurgeMode,
        reference_timestamp: datetime | None = None,
        allow_prod_execute: bool = False,
    ) -> RetentionPurgeReport:

        '''
        Create retention purge report and execute scoped purge actions when requested.

        Args:
        environment (EnvironmentName): Runtime environment value.
        mode (RetentionPurgeMode): Purge mode selector.
        reference_timestamp (datetime | None): Optional retention cutoff reference timestamp.
        allow_prod_execute (bool): Explicit production execute acknowledgement.

        Returns:
        RetentionPurgeReport: Deterministic retention purge execution report.
        '''

        if (
            mode == RetentionPurgeMode.EXECUTE
            and environment == EnvironmentName.PROD
            and allow_prod_execute is False
        ):
            message = (
                'Production retention purge execute mode requires allow_prod_execute=True.'
            )
            raise ValueError(message)

        normalized_reference_timestamp = _utc_now()
        if reference_timestamp is not None:
            normalized_reference_timestamp = _ensure_utc_timestamp(reference_timestamp)

        artifact_reports: list[RetentionPurgeArtifactReport] = []
        with self._session_factory() as session:
            retention_repository = RetentionRepository(session)
            event_repository = EventRepository(session)
            for artifact_type in RETENTION_ARTIFACT_ORDER:
                retention_days = self._get_retention_days(artifact_type, environment)
                cutoff_timestamp = normalized_reference_timestamp - timedelta(days=retention_days)
                candidate_count = retention_repository.count_purge_candidates(
                    environment=environment,
                    artifact_type=artifact_type,
                    cutoff_timestamp=cutoff_timestamp,
                )
                purged_count = 0
                post_purge_rebuild_rows = 0
                if mode == RetentionPurgeMode.EXECUTE and candidate_count != 0:
                    purged_count = retention_repository.purge_candidates(
                        environment=environment,
                        artifact_type=artifact_type,
                        cutoff_timestamp=cutoff_timestamp,
                    )
                    if artifact_type == 'logs' and purged_count != 0:
                        post_purge_rebuild_rows = event_repository.rebuild_event_chain(
                            environment=environment,
                        )
                artifact_reports.append(
                    RetentionPurgeArtifactReport(
                        artifact_type=artifact_type,
                        retention_days=retention_days,
                        cutoff_timestamp=cutoff_timestamp,
                        candidate_count=candidate_count,
                        purged_count=purged_count,
                        post_purge_rebuild_rows=post_purge_rebuild_rows,
                    )
                )

            if mode == RetentionPurgeMode.EXECUTE:
                session.commit()

        total_candidates = sum(report.candidate_count for report in artifact_reports)
        total_purged = sum(report.purged_count for report in artifact_reports)
        return RetentionPurgeReport(
            environment=environment,
            mode=mode,
            reference_timestamp=normalized_reference_timestamp,
            executed_at=_utc_now(),
            artifact_reports=artifact_reports,
            total_candidates=total_candidates,
            total_purged=total_purged,
        )

    def _validate_scope_coverage(self) -> None:
        required_scopes = {
            (artifact_type, environment)
            for artifact_type in RETENTION_ARTIFACT_ORDER
            for environment in (
                EnvironmentName.DEV,
                EnvironmentName.PROD,
                EnvironmentName.CI,
            )
        }
        present_scopes = set(self._retention_days_by_scope.keys())
        if present_scopes != required_scopes:
            missing_scopes = sorted(required_scopes - present_scopes)
            extra_scopes = sorted(present_scopes - required_scopes)
            findings: list[str] = []
            if len(missing_scopes) != 0:
                findings.append(
                    'missing='
                    + ','.join(f'{artifact}:{environment.value}' for artifact, environment in missing_scopes)
                )
            if len(extra_scopes) != 0:
                findings.append(
                    'extra='
                    + ','.join(f'{artifact}:{environment.value}' for artifact, environment in extra_scopes)
                )
            detail_suffix = ''
            if len(findings) != 0:
                detail_suffix = ': ' + '; '.join(findings)
            message = 'Retention purge policy scope coverage is invalid' + detail_suffix
            raise ValueError(message)

    def _get_retention_days(
        self,
        artifact_type: RetentionArtifactType,
        environment: EnvironmentName,
    ) -> int:
        retention_days = self._retention_days_by_scope.get((artifact_type, environment))
        if retention_days is None:
            message = (
                'Retention policy scope not found for '
                f'{artifact_type}:{environment.value}'
            )
            raise ValueError(message)

        return retention_days


def render_retention_purge_report(report: RetentionPurgeReport) -> str:

    '''
    Create canonical JSON representation of retention purge report for operator review.

    Args:
    report (RetentionPurgeReport): Retention purge report payload.

    Returns:
    str: Canonical serialized retention purge report JSON.
    '''

    return json.dumps(
        report.model_dump(mode='json'),
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )


__all__ = [
    'RetentionPurgeArtifactReport',
    'RetentionPurgeMode',
    'RetentionPurgeReport',
    'RetentionPurgeService',
    'render_retention_purge_report',
]
