"""Reusable circuit breaker pattern for external API calls.

States:
    CLOSED   - Normal operation, calls pass through.
    OPEN     - Too many failures, calls are rejected immediately.
    HALF_OPEN - Recovery probe: one call allowed through to test the service.

Usage:
    from circuit_breaker import CircuitBreaker, CircuitOpenError

    maps_cb = CircuitBreaker("google_maps", failure_threshold=5, recovery_timeout=300)

    try:
        result = maps_cb.call(requests.get, url, params=params, timeout=10)
    except CircuitOpenError:
        # Use fallback
    except Exception:
        # Actual API error (already recorded as failure)
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{name}' is OPEN — retry after {retry_after:.0f}s"
        )


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: float = 300):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                # Check if recovery timeout has elapsed
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._transition(self.HALF_OPEN)
            return self._state

    def _transition(self, new_state: str) -> None:
        """Transition to a new state (must be called under lock)."""
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        logger.warning(
            f"Circuit '{self.name}': {old} -> {new_state} "
            f"(failures={self._failure_count})"
        )

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state != self.CLOSED:
                self._transition(self.CLOSED)

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if (self._state == self.CLOSED
                    and self._failure_count >= self.failure_threshold):
                self._transition(self.OPEN)
            elif self._state == self.HALF_OPEN:
                # Probe failed — re-open
                self._transition(self.OPEN)

    def call(self, func, *args, **kwargs):
        """Execute *func* through the circuit breaker.

        Returns the function's result on success.
        Raises CircuitOpenError if the circuit is open.
        Re-raises the original exception on failure (after recording it).
        """
        current = self.state  # may transition OPEN -> HALF_OPEN

        if current == self.OPEN:
            remaining = self.recovery_timeout - (
                time.time() - self._last_failure_time
            )
            raise CircuitOpenError(self.name, max(remaining, 0))

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise
