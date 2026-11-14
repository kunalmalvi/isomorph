"""Restart recovery. Stdlib only.

A process that dies mid run leaves rows in queued or running state that no worker will ever finish. At startup
every such run is marked failed with reason "interrupted by restart", and stages that were running are failed with
the same reason. Completed stage outputs are kept, so the user can rerun downstream instead of starting over.

Call this once, before the job runner accepts work. With several API processes sharing one database this would
fail runs another live process owns, so run it from a single process or add a heartbeat first (not implemented).
"""
from __future__ import annotations

from typing import List

from services.run_store import RunStore

INTERRUPTED = "interrupted by restart"


def recover_interrupted_runs(store: RunStore) -> List[str]:
    recovered = []
    for run_id in store.active_run_ids():
        run = store.get(run_id)
        if run is None:
            continue
        run.status, run.error = "failed", INTERRUPTED
        for st in run.stages.values():
            if st.status == "running":
                st.status, st.error = "failed", INTERRUPTED
        store.save(run)
        recovered.append(run_id)
    return recovered
