from __future__ import annotations

from threading import Lock

from fastapi import FastAPI
from opentelemetry import propagate
from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.textmap import TextMapPropagator
from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.trace.sampling import Sampler
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor

from agent1.config.settings import Settings
from agent1.config.settings import get_settings

TELEMETRY_TRACER_NAME = 'agent1.telemetry'
_TRACER_PROVIDER: TracerProvider | None = None
_INITIALIZATION_LOCK = Lock()


def _resolve_sampler(sampler_name: str) -> Sampler:
    if sampler_name.strip().lower() == 'always_off':
        return ALWAYS_OFF

    return ALWAYS_ON


def _configure_propagators(propagators: str) -> None:
    names = {name.strip().lower() for name in propagators.split(',') if name.strip() != ''}
    selected: list[TextMapPropagator] = []
    if 'tracecontext' in names:
        selected.append(TraceContextTextMapPropagator())
    if 'baggage' in names:
        selected.append(W3CBaggagePropagator())
    if len(selected) == 0:
        return

    propagate.set_global_textmap(CompositePropagator(selected))


def _create_tracer_provider(settings: Settings) -> TracerProvider:
    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=_resolve_sampler(settings.otel_traces_sampler),
    )
    if settings.sentry_python_dsn.strip() != '':
        tracer_provider.add_span_processor(SentrySpanProcessor())
    return tracer_provider


def initialize_telemetry(application: FastAPI, settings: Settings | None = None) -> bool:

    '''
    Create OpenTelemetry runtime initialization and FastAPI instrumentation.

    Args:
    application (FastAPI): FastAPI application instance.
    settings (Settings | None): Optional runtime settings override.

    Returns:
    bool: True when telemetry initialization completed.
    '''

    runtime_settings = settings or get_settings()
    global _TRACER_PROVIDER

    with _INITIALIZATION_LOCK:
        if _TRACER_PROVIDER is None:
            _TRACER_PROVIDER = _create_tracer_provider(runtime_settings)
            trace.set_tracer_provider(_TRACER_PROVIDER)
            _configure_propagators(runtime_settings.otel_propagators)

    if getattr(application, '_is_instrumented_by_opentelemetry', False) is False:
        FastAPIInstrumentor.instrument_app(application, tracer_provider=_TRACER_PROVIDER)

    return True


def get_tracer() -> trace.Tracer:

    '''
    Create telemetry tracer instance for custom runtime spans.

    Returns:
    trace.Tracer: OpenTelemetry tracer.
    '''

    return trace.get_tracer(TELEMETRY_TRACER_NAME)


def get_otel_trace_id() -> str | None:

    '''
    Create current OpenTelemetry trace identifier for correlation fields.

    Returns:
    str | None: Current trace identifier in hex format when available.
    '''

    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid is False:
        return None

    return format(span_context.trace_id, '032x')


__all__ = ['get_otel_trace_id', 'get_tracer', 'initialize_telemetry']
