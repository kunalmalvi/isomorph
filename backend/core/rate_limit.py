"""Sliding window rate limiter with an injectable clock. Stdlib only, thread safe, in memory."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
import ipaddress
from typing import Callable, Deque, Dict, Iterable, Optional, Tuple


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


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(ip, trusted: Iterable[str]) -> bool:
    for entry in trusted:
        try:
            if ip in ipaddress.ip_network(entry.strip(), strict=False):
                return True
        except ValueError:
            continue
    return False


def client_key(peer: Optional[str], forwarded_for: Optional[str] = None, trusted_proxies: Iterable[str] = ()) -> str:
    """Rate limit key for a request.

    X-Forwarded-For is client controlled, so it is honored only when the direct peer is a trusted proxy
    (entries are IPs or CIDR networks). The header is walked from the right: trusted proxies are skipped and the
    first address that is not trusted is the client. A malformed entry stops the walk and the peer is used.
    """
    trusted = tuple(trusted_proxies)
    peer_ip = _parse_ip(peer) if peer else None
    if peer_ip is None:
        return peer or "unknown"
    if not trusted or not forwarded_for or not _is_trusted(peer_ip, trusted):
        return str(peer_ip)
    hops = [h for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        ip = _parse_ip(hop)
        if ip is None:
            return str(peer_ip)
        if not _is_trusted(ip, trusted):
            return str(ip)
    return str(peer_ip)
