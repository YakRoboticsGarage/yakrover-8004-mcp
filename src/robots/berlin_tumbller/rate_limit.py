"""In-memory sliding-window rate limiter for motor commands.

Applied at the MCP server level (firmware is unauthenticated in v1, so this
is our primary abuse ceiling). Default: 10 commands per rolling 60 seconds.
Resets on process restart — acceptable for v1; persistent counters can be
added if we ever see abuse that straddles deploys.
"""

import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def allow(self, now: float | None = None) -> bool:
        """Record a request if under the cap. Returns True if allowed."""
        t = now if now is not None else time.monotonic()
        self._evict(t)
        if len(self._timestamps) >= self.max_requests:
            return False
        self._timestamps.append(t)
        return True

    def remaining(self, now: float | None = None) -> int:
        t = now if now is not None else time.monotonic()
        self._evict(t)
        return max(0, self.max_requests - len(self._timestamps))
