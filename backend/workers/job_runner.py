"""Background job runner with persisted stage progress. Stdlib only.

Jobs execute an Orchestrator run on a thread pool. Progress is persisted by the orchestrator's RunStore after
every stage, so any process sharing the store can report it. Cancellation is cooperative (checked between stages).
"""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional

from services.orchestrator import Orchestrator

ACTIVE = ("queued", "running")


class JobRunner:
    def __init__(self, orchestrator: Orchestrator, max_workers: int = 2, synchronous: bool = False):
        self.orch = orchestrator
        self.synchronous = synchronous
        self._pool = None if synchronous else ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="isomorph-job")
        self._futures: Dict[str, Future] = {}
        self._cancel: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, run_id: str, action: Optional[Callable[[Callable[[], bool]], object]] = None) -> None:
        """Queue a run. `action(should_cancel)` defaults to orchestrator.run."""
        with self._lock:
            f = self._futures.get(run_id)
            if f is not None and not f.done():
                raise RuntimeError("run already in progress")
            ev = self._cancel[run_id] = threading.Event()
        act = action or (lambda should_cancel: self.orch.run(run_id, should_cancel))

        def job():
            try:
                act(ev.is_set)
            except Exception as e:  # persist unexpected failure so the run never stays "running" forever
                run = self.orch.store.get(run_id)
                if run is not None:
                    run.status, run.error = "failed", f"unexpected error: {type(e).__name__}: {e}"
                    self.orch.store.save(run)

        if self.synchronous:
            job()
            return
        with self._lock:
            self._futures[run_id] = self._pool.submit(job)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            ev = self._cancel.get(run_id)
        if ev is None:
            return False
        ev.set()
        return True

    def wait(self, run_id: str, timeout: Optional[float] = None) -> None:
        f = self._futures.get(run_id)
        if f is not None:
            f.result(timeout)

    def is_active(self, run_id: str) -> bool:
        f = self._futures.get(run_id)
        return f is not None and not f.done()

    def shutdown(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True)
