"""Server-sent events helpers. Stdlib only."""
from __future__ import annotations

import json
import time
from typing import Callable, Iterator, Optional

TERMINAL = ("done", "failed", "cancelled")


def format_sse(event: str, data: dict, event_id: Optional[int] = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


MIN_INTERVAL, MAX_INTERVAL = 0.25, 5.0
DEFAULT_MAX_SECONDS = 30.0
RETRY_MS = 2000


def parse_last_event_id(value: Optional[str]) -> int:
    """Last-Event-ID header to an int. Missing or malformed values mean 0 (start fresh)."""
    try:
        n = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    return n if 0 <= n < 10**9 else 0


def progress_stream(get_progress: Callable[[], Optional[dict]], interval: float = 1.0, max_seconds: float = DEFAULT_MAX_SECONDS,
                    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                    last_event_id: int = 0) -> Iterator[str]:
    """Yield an SSE `progress` event whenever the snapshot changes and a final `end` event at a terminal status.

    `get_progress` returns the snapshot dict (see RunRecord.progress) or None when the run disappeared.

    A connection is bounded: polling happens every `interval` seconds (clamped to 0.25..5) and the stream closes with a
    `timeout` event after `max_seconds`, so a request never holds a worker thread for long. EventSource reconnects on
    its own; the `retry:` field sets the delay and `last_event_id` (from the Last-Event-ID header) continues numbering.
    The first poll of a reconnect always sends the current snapshot, so no state is lost across the gap.
    """
    interval = min(MAX_INTERVAL, max(MIN_INTERVAL, interval))
    start, last, n = clock(), None, last_event_id
    yield f"retry: {RETRY_MS}\n\n"
    while True:
        snap = get_progress()
        if snap is None:
            yield format_sse("error", {"code": "not_found", "message": "run not found"}, n + 1)
            return
        if snap != last:
            n += 1
            yield format_sse("progress", snap, n)
            last = snap
        if snap["status"] in TERMINAL:
            yield format_sse("end", {"status": snap["status"]}, n + 1)
            return
        if clock() - start >= max_seconds:
            yield format_sse("timeout", {"message": "stream time limit reached, reconnect to continue", "reconnect": True}, n + 1)
            return
        sleep(interval)
