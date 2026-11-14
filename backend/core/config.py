"""Runtime settings read from environment variables. Stdlib only so it is testable without pydantic.

Local deterministic mode is the default: AI_PROVIDER=local needs no API key and no network.
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

DEV_SECRET = "dev-only-secret-change-me-0123456789abcdef"
PROVIDERS = ("local", "openai", "gemini", "anthropic")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    secret_key: str = DEV_SECRET
    database_url: str = "sqlite:///./isomorph.db"
    access_token_ttl_seconds: int = 3600
    ai_provider: str = "local"
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 2
    ai_requests_per_minute: int = 30
    api_requests_per_minute: int = 120
    auth_attempts_per_minute: int = 10
    max_upload_bytes: int = 5 * 1024 * 1024
    data_dir: Optional[str] = None
    cors_origins: tuple = ("http://localhost:3000",)
    worker_threads: int = 2
    trusted_proxies: tuple = ()
    state_dir: Optional[str] = None
    sse_max_seconds: float = 30.0

    def validate(self) -> "Settings":
        if self.ai_provider not in PROVIDERS:
            raise ConfigError(f"AI_PROVIDER must be one of {PROVIDERS}")
        if len(self.secret_key) < 32:
            raise ConfigError("ISOMORPH_SECRET_KEY must be at least 32 characters")
        if self.environment == "production" and self.secret_key == DEV_SECRET:
            raise ConfigError("ISOMORPH_SECRET_KEY must be set explicitly in production")
        for entry in self.trusted_proxies:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                raise ConfigError(f"TRUSTED_PROXIES entry is not an IP or CIDR network: {entry!r}")
        if not 1 <= self.sse_max_seconds <= 600:
            raise ConfigError("SSE_MAX_SECONDS must be between 1 and 600")
        return self

    def api_key_for(self, provider: str) -> Optional[str]:
        return {"openai": self.openai_api_key, "gemini": self.gemini_api_key,
                "anthropic": self.anthropic_api_key}.get(provider)


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    e = os.environ if env is None else env
    g = e.get
    return Settings(
        environment=g("ISOMORPH_ENV", "development"),
        secret_key=g("ISOMORPH_SECRET_KEY", DEV_SECRET),
        database_url=g("DATABASE_URL", "sqlite:///./isomorph.db"),
        access_token_ttl_seconds=int(g("ACCESS_TOKEN_TTL_SECONDS", "3600")),
        ai_provider=g("AI_PROVIDER", "local"),
        openai_api_key=g("OPENAI_API_KEY") or None,
        gemini_api_key=g("GEMINI_API_KEY") or None,
        anthropic_api_key=g("ANTHROPIC_API_KEY") or None,
        ai_timeout_seconds=float(g("AI_TIMEOUT_SECONDS", "30")),
        ai_max_retries=int(g("AI_MAX_RETRIES", "2")),
        ai_requests_per_minute=int(g("AI_REQUESTS_PER_MINUTE", "30")),
        api_requests_per_minute=int(g("API_REQUESTS_PER_MINUTE", "120")),
        auth_attempts_per_minute=int(g("AUTH_ATTEMPTS_PER_MINUTE", "10")),
        max_upload_bytes=int(g("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
        data_dir=g("ISOMORPH_DATA_DIR") or None,
        cors_origins=tuple(x.strip() for x in g("CORS_ORIGINS", "http://localhost:3000").split(",") if x.strip()),
        worker_threads=int(g("WORKER_THREADS", "2")),
        trusted_proxies=tuple(x.strip() for x in g("TRUSTED_PROXIES", "").split(",") if x.strip()),
        state_dir=g("ISOMORPH_STATE_DIR") or None,
        sse_max_seconds=float(g("SSE_MAX_SECONDS", "30")),
    ).validate()
