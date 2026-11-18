"""Application wiring shared by the server and the CLI. Stdlib only."""
from __future__ import annotations

import os
from typing import Optional

from ai_providers import get_provider
from core.config import load_settings
from core.errors import Conflict, NotFound, ValidationFailed
from services.knowledge import KnowledgeBase, default_knowledge
from services.orchestrator import STAGES, Orchestrator
from services.reports import build_report, report_markdown
from services.sqlite_store import SqliteAnnotationStore, SqliteDatabase, SqliteRunStore
from workers.job_runner import JobRunner
from workers.recovery import recover_interrupted_runs

from .config import AppConfig

TERMINAL = ("done", "failed", "cancelled")


class App:
    def __init__(self, config: AppConfig, knowledge: Optional[KnowledgeBase] = None, synchronous: bool = False):
        self.config = config
        config.ensure_dirs()
        self.db = SqliteDatabase(config.db_path)
        self.store = SqliteRunStore(self.db)
        self.annotations = SqliteAnnotationStore(self.db)
        self.settings = load_settings()
        self.kb = knowledge or default_knowledge()
        self.orch = Orchestrator(self.store, self.kb, provider_factory=lambda name: get_provider(self.settings, name))
        # a process that died mid run leaves queued/running rows no worker will finish
        self.recovered = recover_interrupted_runs(self.store)
        self.jobs = JobRunner(self.orch, max_workers=config.worker_threads, synchronous=synchronous)

    # ------------------------------------------------------------------ runs
    def start_run(self, text=None, problem=None, title: str = "", config: Optional[dict] = None) -> dict:
        run = self.orch.create_run(text=text, problem=problem, title=title, config=config)
        self.jobs.submit(run.id)
        return {"id": run.id, "status": run.status}

    def analyze(self, text: str, title: str = "", config: Optional[dict] = None) -> dict:
        """Run a discovery to completion in the calling thread and return the run record dict."""
        run = self.orch.create_run(text=text, title=title, config=config)
        self.orch.run(run.id)
        return self.store.get(run.id).to_dict()

    def require_run(self, run_id: str):
        run = self.store.get(run_id) if _valid_id(run_id) else None
        if run is None:
            raise NotFound("discovery not found")
        return run

    def _requeue(self, run_id: str, action) -> dict:
        if self.jobs.is_active(run_id):
            raise Conflict("this discovery is already running")
        run = self.require_run(run_id)
        if run.status in ("queued", "running"):
            raise Conflict("this discovery is already running")
        run.status, run.error = "queued", None
        self.store.save(run)
        self.jobs.submit(run_id, action)
        return {"id": run_id, "status": "queued"}

    def rerun(self, run_id: str, stage: str, mode: str) -> dict:
        if stage not in STAGES:
            raise NotFound(f"unknown stage '{stage}'")
        if mode == "downstream":
            return self._requeue(run_id, lambda cancel: self.orch.rerun_downstream(run_id, stage, cancel))
        if mode == "from":
            return self._requeue(run_id, lambda cancel: self.orch.rerun_from(run_id, stage, cancel))
        raise ValidationFailed("mode must be 'downstream' or 'from'")

    def resume(self, run_id: str) -> dict:
        return self._requeue(run_id, lambda cancel: self.orch.run(run_id, cancel))

    def cancel(self, run_id: str) -> dict:
        run = self.require_run(run_id)
        if run.status not in ("queued", "running"):
            raise Conflict(f"discovery is {run.status}, nothing to cancel")
        self.jobs.cancel(run_id)
        return {"id": run_id, "status": run.status, "cancel_requested": True}

    def delete_run(self, run_id: str) -> None:
        run = self.require_run(run_id)
        if run.status in ("queued", "running") and self.jobs.is_active(run_id):
            raise Conflict("cancel the discovery before deleting it")
        self.store.delete(run_id)

    # ------------------------------------------------------------------ reports and annotations
    def report(self, run_id: str, fmt: str = "md"):
        run = self.require_run(run_id)
        title = (run.input or {}).get("title") or "ISOMORPH discovery report"
        rep = build_report(title, run.to_dict())
        notes = self.visible_annotations(run_id)
        if fmt == "json":
            rep["annotations"] = notes
            return rep
        md = report_markdown(rep)
        if notes:
            lines = ["## Reviewer decisions (provenance: user)"]
            for h, a in sorted(notes.items()):
                lines.append(f"- {h}: {a['decision']}" + (f". {a['note']}" if a["note"] else ""))
            md = md.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"
        return md

    def hypothesis_ids(self, run_id: str) -> set:
        run = self.require_run(run_id)
        out = run.stages["hypothesis_generation"].output
        return {h.get("id") for h in (out or {}).get("hypotheses", [])}

    def visible_annotations(self, run_id: str) -> dict:
        """Notes are keyed by positional hypothesis id, so hide those whose hypothesis no longer exists."""
        current = self.hypothesis_ids(run_id)
        return {k: v for k, v in self.annotations.list(run_id).items() if k in current}

    # ------------------------------------------------------------------ misc
    def health(self) -> dict:
        from . import __version__
        return {"status": "ok", "version": __version__, "schema_version": self.db.schema_version(),
                "runs": self.store.list_runs(limit=1)["total"]}

    def close(self) -> None:
        self.jobs.shutdown()


def _valid_id(run_id: str) -> bool:
    return bool(run_id) and len(run_id) <= 64 and all(c.isalnum() or c in "-_" for c in run_id)


def knowledge_summary(kb: KnowledgeBase) -> dict:
    return {"systems": len(kb.systems), "domains": len(kb.domains_doc.get("domains", []))}


def data_files_present(home: str) -> bool:
    return os.path.isdir(home)
