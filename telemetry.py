"""Local-first OpenTelemetry setup for tracing and metrics."""

from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
except Exception:  # pragma: no cover
    trace = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except Exception:  # pragma: no cover
    OTLPSpanExporter = None

try:
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
except Exception:  # pragma: no cover
    PrometheusMetricReader = None

try:
    from opentelemetry.sdk.metrics import MeterProvider
except Exception:  # pragma: no cover
    MeterProvider = None

_configured = False


def configure_opentelemetry(service_name: str = "stock-alert-bot") -> dict[str, Any]:
    """Configure tracing and optional OTel metrics; safe to call multiple times."""
    global _configured
    if _configured:
        return {"configured": True, "mode": "existing"}

    if trace is None or Resource is None or TracerProvider is None or BatchSpanProcessor is None or ConsoleSpanExporter is None:
        _configured = True
        return {"configured": True, "mode": "disabled", "reason": "opentelemetry_packages_missing"}

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    if endpoint and OTLPSpanExporter is not None:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        mode = "otlp"
    else:
        exporter = ConsoleSpanExporter()
        mode = "console"

    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)

    if MeterProvider is not None:
        metric_readers = []
        if os.environ.get("OTEL_ENABLE_PROMETHEUS", "0").strip().lower() in {"1", "true", "yes", "on"}:
            if PrometheusMetricReader is not None:
                metric_readers.append(PrometheusMetricReader())
        meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        try:
            from opentelemetry import metrics

            metrics.set_meter_provider(meter_provider)
        except Exception:
            pass

    _configured = True
    return {"configured": True, "mode": mode, "endpoint": endpoint or None}


class _NoopTracer:
    def start_as_current_span(self, name: str):
        return nullcontext()


def get_tracer(name: str = "stock-alert-bot"):
    if trace is None:
        return _NoopTracer()
    try:
        return trace.get_tracer(name)
    except Exception:
        return _NoopTracer()
