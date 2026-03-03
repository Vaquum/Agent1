from __future__ import annotations

from fastapi import FastAPI

from agent1.config.settings import Settings
from agent1.core.services.telemetry_runtime import get_otel_trace_id
from agent1.core.services.telemetry_runtime import get_tracer
from agent1.core.services.telemetry_runtime import initialize_telemetry


def test_initialize_telemetry_instruments_fastapi_application() -> None:
    application = FastAPI()
    enabled = initialize_telemetry(
        application,
        settings=Settings(
            sentry_python_dsn='',
            otel_service_name='agent1-backend',
            otel_traces_sampler='always_on',
            otel_propagators='tracecontext,baggage',
        ),
    )

    assert enabled is True
    assert getattr(application, '_is_instrumented_by_opentelemetry', False) is True


def test_get_otel_trace_id_returns_hex_value_with_active_span() -> None:
    application = FastAPI()
    initialize_telemetry(
        application,
        settings=Settings(
            sentry_python_dsn='',
            otel_service_name='agent1-backend',
            otel_traces_sampler='always_on',
            otel_propagators='tracecontext,baggage',
        ),
    )

    assert get_otel_trace_id() is None
    with get_tracer().start_as_current_span('test_span'):
        trace_id = get_otel_trace_id()
        assert trace_id is not None
        assert len(trace_id) == 32
    assert get_otel_trace_id() is None
