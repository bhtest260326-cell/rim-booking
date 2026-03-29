"""
trace_context.py — Lightweight distributed tracing via thread-local storage.

Provides trace ID propagation and span tracking across the processing pipeline
without any external tracing libraries.
"""

import threading
import time
import logging
from contextlib import contextmanager

_local = threading.local()
logger = logging.getLogger(__name__)


def get_trace_id():
    """Return the current trace ID, or None if not set."""
    return getattr(_local, 'trace_id', None)


def set_trace_id(trace_id):
    """Set the trace ID for the current thread."""
    _local.trace_id = trace_id


def get_span():
    """Return the current span name, or None if not set."""
    return getattr(_local, 'span', None)


def set_span(span):
    """Set the current span name for the current thread."""
    _local.span = span


def get_trace_context():
    """Return a dict with the current trace_id and span."""
    return {
        'trace_id': get_trace_id(),
        'span': get_span(),
    }


@contextmanager
def trace_span(name):
    """Context manager that logs span start/end with duration.

    Usage:
        with trace_span("process_email"):
            ...
    """
    previous_span = get_span()
    set_span(name)
    trace_id = get_trace_id()
    logger.info("span_start", extra={'span_name': name, 'trace_id': trace_id})
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "span_end",
            extra={'span_name': name, 'trace_id': trace_id, 'duration_ms': duration_ms},
        )
        set_span(previous_span)


class TraceContextFilter(logging.Filter):
    """Logging filter that injects trace_id and span into every log record."""

    def filter(self, record):
        record.trace_id = get_trace_id()
        record.span = get_span()
        return True
