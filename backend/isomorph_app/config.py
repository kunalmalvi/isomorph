"""One data directory for everything the app writes. Stdlib only.

Resolution order for the directory: explicit argument, ISOMORPH_HOME, then ~/.isomorph.
Layout: isomorph.db (runs and notes), uploads/, backups/, learning/ (evidence log, learned versions, audit).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_PORT = 8765
MAX_BODY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    home: str
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    token: Optional[str] = None
    max_body_bytes: int = MAX_BODY_BYTES
    worker_threads: int = 2
    sse_max_seconds: float = 15.0
    static_dir: Optional[str] = None

    @property
    def db_path(self) -> str:
        return os.path.join(self.home, "isomorph.db")

    @property
    def uploads_dir(self) -> str:
        return os.path.join(self.home, "uploads")

    @property
    def backups_dir(self) -> str:
        return os.path.join(self.home, "backups")

    @property
    def learning_dir(self) -> str:
        return os.path.join(self.home, "learning")

    def ensure_dirs(self) -> None:
        for d in (self.home, self.uploads_dir, self.backups_dir, self.learning_dir):
            os.makedirs(d, exist_ok=True)


def resolve_home(explicit: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> str:
    e = os.environ if env is None else env
    return os.path.abspath(os.path.expanduser(explicit or e.get("ISOMORPH_HOME") or "~/.isomorph"))


def _int(v: Optional[str], default: int) -> int:
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


def load_config(home: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None,
                env: Optional[Mapping[str, str]] = None) -> AppConfig:
    e = os.environ if env is None else env
    return AppConfig(home=resolve_home(home, e), host=host or e.get("ISOMORPH_HOST") or "127.0.0.1",
                     port=port if port is not None else _int(e.get("ISOMORPH_PORT"), DEFAULT_PORT),
                     token=e.get("ISOMORPH_TOKEN") or None, max_body_bytes=_int(e.get("ISOMORPH_MAX_BODY_BYTES"), MAX_BODY_BYTES),
                     worker_threads=_int(e.get("ISOMORPH_WORKERS"), 2), sse_max_seconds=float(_int(e.get("SSE_MAX_SECONDS"), 15)))


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")
