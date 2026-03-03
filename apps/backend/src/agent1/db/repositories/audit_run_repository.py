from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import AuditRunRecord
from agent1.core.contracts import AuditRunStatus
from agent1.core.contracts import EnvironmentName
from agent1.db.models import AuditRunModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for audit-run persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class AuditRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_audit_run(self, record: AuditRunRecord) -> AuditRunModel:

        '''
        Create persisted audit-run row from typed audit-run contract.

        Args:
        record (AuditRunRecord): Typed audit-run contract to persist.

        Returns:
        AuditRunModel: Persisted audit-run model.
        '''

        normalized_completed_at: datetime | None = None
        if record.completed_at is not None:
            normalized_completed_at = _ensure_utc_timestamp(record.completed_at)

        model = AuditRunModel(
            audit_run_id=record.audit_run_id,
            environment=record.environment,
            audit_type=record.audit_type,
            status=record.status,
            started_at=_ensure_utc_timestamp(record.started_at),
            completed_at=normalized_completed_at,
            snapshot=record.snapshot,
            updated_at=_utc_now(),
        )
        self._session.add(model)
        self._session.flush()
        return model

    def list_audit_runs(
        self,
        environment: EnvironmentName,
        limit: int,
        offset: int = 0,
        audit_type: str | None = None,
        status: AuditRunStatus | None = None,
    ) -> list[AuditRunModel]:

        '''
        Create audit-run list for one environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.
        audit_type (str | None): Optional audit type filter.
        status (AuditRunStatus | None): Optional audit-run status filter.

        Returns:
        list[AuditRunModel]: Ordered audit-run rows.
        '''

        query = self._session.query(AuditRunModel).filter(AuditRunModel.environment == environment)
        if audit_type is not None and audit_type.strip() != '':
            query = query.filter(AuditRunModel.audit_type == audit_type.strip())
        if status is not None:
            query = query.filter(AuditRunModel.status == status)

        return query.order_by(AuditRunModel.started_at.desc()).offset(offset).limit(limit).all()


__all__ = ['AuditRunRepository']
