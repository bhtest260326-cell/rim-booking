"""
request_metrics.py -- Lightweight in-memory ring buffer for API response time tracking.

Stores the last 1000 request timings per endpoint. Designed to have near-zero
impact on request performance (no I/O, no locks for the common append path).
"""

import time
import threading
from collections import defaultdict

_BUFFER_SIZE = 1000

# Global ring buffer: endpoint -> list of (timestamp, duration_ms)
_timings: dict = defaultdict(list)
_lock = threading.Lock()

# Server start time for uptime calculation
_start_time = time.time()


def record_timing(endpoint: str, duration_ms: float) -> None:
    """Append a timing entry. Trims to BUFFER_SIZE periodically."""
    entry = (time.time(), duration_ms)
    buf = _timings[endpoint]
    buf.append(entry)
    # Trim when buffer exceeds 2x size (amortised cost)
    if len(buf) > _BUFFER_SIZE * 2:
        with _lock:
            _timings[endpoint] = buf[-_BUFFER_SIZE:]


def get_endpoint_stats() -> dict:
    """Return per-endpoint average response times for last 1h and 24h windows."""
    now = time.time()
    cutoff_1h = now - 3600
    cutoff_24h = now - 86400
    results = {}

    for endpoint, buf in list(_timings.items()):
        times_1h = []
        times_24h = []
        for ts, dur in buf:
            if ts >= cutoff_24h:
                times_24h.append(dur)
                if ts >= cutoff_1h:
                    times_1h.append(dur)

        results[endpoint] = {
            'avg_1h': round(sum(times_1h) / len(times_1h), 1) if times_1h else None,
            'avg_24h': round(sum(times_24h) / len(times_24h), 1) if times_24h else None,
            'count_1h': len(times_1h),
            'count_24h': len(times_24h),
            'p95_1h': round(sorted(times_1h)[int(len(times_1h) * 0.95)] if len(times_1h) >= 2 else (times_1h[0] if times_1h else 0), 1) if times_1h else None,
        }

    return results


def get_uptime_seconds() -> float:
    return time.time() - _start_time
