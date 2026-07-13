"""Low-overhead rolling receive FPS measurement."""

from __future__ import annotations

from collections import deque


class RollingFps:
    def __init__(self, window_seconds: float = 1.0) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._window_ns = int(window_seconds * 1_000_000_000)
        self._timestamps: deque[int] = deque()

    def add(self, timestamp_ns: int) -> float:
        self._timestamps.append(timestamp_ns)
        cutoff = timestamp_ns - self._window_ns
        while len(self._timestamps) > 1 and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return self.value

    @property
    def value(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        elapsed = self._timestamps[-1] - self._timestamps[0]
        return (len(self._timestamps) - 1) * 1_000_000_000 / elapsed if elapsed > 0 else 0.0

    def reset(self) -> None:
        self._timestamps.clear()
