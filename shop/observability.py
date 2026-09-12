"""Small, privacy-preserving operational telemetry surface.

Metrics are derived from durable state where possible, so a restarted API
process does not make queue and outcome graphs disappear.  The optional
OpenTelemetry dependency is deliberately isolated here: telemetry outages
must never affect shopper requests.
"""
from __future__ import annotations

import time
from contextvars import ContextVar
from threading import Lock
from uuid import uuid4

from shop import store

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")
_lock = Lock()
_requests: dict[tuple[str, str], int] = {}
_durations: dict[str, tuple[int, float]] = {}


def request_trace_id() -> str:
    return _trace_id.get()


def begin_request() -> tuple[str, float, object]:
    trace_id = uuid4().hex
    token = _trace_id.set(trace_id)
    return trace_id, time.perf_counter(), token


def finish_request(method: str, status: int, started: float, token: object) -> None:
    with _lock:
        key = (method, str(status))
        _requests[key] = _requests.get(key, 0) + 1
        count, total = _durations.get(method, (0, 0.0))
        _durations[method] = (count + 1, total + time.perf_counter() - started)
    _trace_id.reset(token)  # type: ignore[arg-type]


def _line(name: str, value: object, **labels: object) -> str:
    rendered = "".join(f'{key}="{str(value).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for key, value in labels.items())
    suffix = f"{{{rendered}}}" if rendered else ""
    return f"{name}{suffix} {value}"


def prometheus() -> str:
    """Render stable operational signals in Prometheus text format."""
    lines = [
        "# HELP shop_http_requests_total HTTP requests handled by status.",
        "# TYPE shop_http_requests_total counter",
    ]
    with _lock:
        for (method, status), count in sorted(_requests.items()):
            lines.append(_line("shop_http_requests_total", count, method=method, status=status))
        durations = dict(_durations)
    lines += [
        "# HELP shop_http_request_duration_seconds_sum HTTP request duration sum.",
        "# TYPE shop_http_request_duration_seconds_sum counter",
    ]
    for method, (count, total) in sorted(durations.items()):
        lines.append(_line("shop_http_request_duration_seconds_count", count, method=method))
        lines.append(_line("shop_http_request_duration_seconds_sum", total, method=method))
    try:
        durable = store.telemetry_snapshot()
        for name, value in durable.items():
            lines.append(_line(f"shop_{name}", value))
    except Exception:
        # Scraping must remain safe during a database restart.
        lines.append(_line("shop_telemetry_database_up", 0))
    else:
        lines.append(_line("shop_telemetry_database_up", 1))
    return "\n".join(lines) + "\n"
