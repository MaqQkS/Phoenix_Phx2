"""Thread-safe run-wide byte ceiling shared by Helius WSS and HTTP."""

from __future__ import annotations

import threading


SOURCE_WSS = "WSS"
SOURCE_HTTP = "HTTP"
BYTE_SOURCES = (SOURCE_WSS, SOURCE_HTTP)


class HeliusByteBudget:
    """Reserve observed response bytes without ever exceeding the ceiling."""

    __slots__ = (
        "_ceiling",
        "_http_bytes",
        "_http_estimated_credits",
        "_lock",
        "_overflow_attempted",
        "_reached",
        "_wss_bytes",
        "_wss_estimated_credits",
    )

    def __init__(self, ceiling: int) -> None:
        if (
            isinstance(ceiling, bool)
            or not isinstance(ceiling, int)
            or not 1 <= ceiling <= 10_000_000_000
        ):
            raise ValueError("Helius byte ceiling is out of range")
        self._ceiling = ceiling
        self._wss_bytes = 0
        self._http_bytes = 0
        self._wss_estimated_credits = 0.0
        self._http_estimated_credits = 0.0
        self._reached = False
        self._overflow_attempted = False
        self._lock = threading.Lock()

    def consume(self, byte_count: int, *, source: str) -> bool:
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
            or source not in BYTE_SOURCES
        ):
            raise ValueError("Helius byte observation is invalid")
        with self._lock:
            used = self._wss_bytes + self._http_bytes
            if used + byte_count > self._ceiling:
                self._reached = True
                self._overflow_attempted = True
                return False
            if source == SOURCE_WSS:
                self._wss_bytes += byte_count
            else:
                self._http_bytes += byte_count
            if self._wss_bytes + self._http_bytes >= self._ceiling:
                self._reached = True
            return True

    def record_estimated_credits(
        self,
        value: object,
        *,
        source: str,
    ) -> None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or float(value) < 0
            or source not in BYTE_SOURCES
        ):
            raise ValueError("Helius credit observation is invalid")
        with self._lock:
            if source == SOURCE_WSS:
                self._wss_estimated_credits += float(value)
            else:
                self._http_estimated_credits += float(value)

    @property
    def reached(self) -> bool:
        with self._lock:
            return self._reached

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            used = self._wss_bytes + self._http_bytes
            return {
                "ceiling": self._ceiling,
                "used_bytes": used,
                "wss_bytes": self._wss_bytes,
                "http_bytes": self._http_bytes,
                "wss_estimated_credits": self._wss_estimated_credits,
                "http_estimated_credits": self._http_estimated_credits,
                "estimated_credits": (
                    self._wss_estimated_credits
                    + self._http_estimated_credits
                ),
                "remaining_bytes": self._ceiling - used,
                "reached": self._reached,
                "overflow_attempted": self._overflow_attempted,
            }

    def __repr__(self) -> str:
        snapshot = self.snapshot()
        return (
            "HeliusByteBudget("
            f"ceiling={snapshot['ceiling']!r}, "
            f"used_bytes={snapshot['used_bytes']!r}, "
            f"reached={snapshot['reached']!r})"
        )


__all__ = (
    "BYTE_SOURCES",
    "HeliusByteBudget",
    "SOURCE_HTTP",
    "SOURCE_WSS",
)
