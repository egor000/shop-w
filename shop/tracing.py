"""Optional OpenTelemetry setup with a no-op fallback for local tests."""
from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any


@contextmanager
def span(name: str, **attributes: str) -> Iterator[Any]:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        tracer = trace.get_tracer("shop-assistant")
        with tracer.start_as_current_span(name, attributes=attributes):
            yield None
    except ImportError:
        yield None


def configure() -> None:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
        provider = TracerProvider(resource=Resource.create({"service.name": "shop-assistant"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
    except ImportError:
        # The application remains fully functional when an exporter is absent.
        return
