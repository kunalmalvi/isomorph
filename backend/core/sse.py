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


def progress_stream(get_progress: Callable[[], Optional[dict]], interval: float = 0.5, max_seconds: float = 600.0,
                    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> Iterator[str]:
    """Yield an SSE `progress` event whenever the snapshot changes and a final `end` event at a terminal status.

    `get_progress` returns the snapshot dict (see RunRecord.progress) or None when the run disappeared.
    """
    start, last, n = clock(), None, 0
    while True:
        snap = get_progress()
        if snap is None:
            yield format_sse("error", {"code": "not_found", "message": "run not found"}, n)
            return
        if snap != last:
            n += 1
            yield format_sse("progress", snap, n)
            last = snap
        if snap["status"] in TERMINAL:
            yield format_sse("end", {"status": snap["status"]}, n + 1)
            return
        if clock() - start > max_seconds:
            yield format_sse("timeout", {"message": "stream time limit reached, reconnect to continue"}, n + 1)
            return
        sleep(interval)
