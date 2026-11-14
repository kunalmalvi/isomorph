"""Sliding window rate limiter with an injectable clock. Stdlib only, thread safe, in memory."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        if limit < 1 or window_seconds <= 0:
            raise ValueError("limit must be >= 1 and window > 0")
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, float]:
        """Record a hit if allowed. Returns (allowed, retry_after_seconds)."""
        now = self.clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(0.0, self.window - (now - q[0]))
            q.append(now)
            return True, 0.0

    def remaining(self, key: str) -> int:
        now = self.clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            return max(0, self.limit - len(q))

    def reset(self, key: str = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
