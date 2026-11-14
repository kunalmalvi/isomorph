"""Provider selection. Default is the local deterministic provider.

A remote provider that is requested but not configured raises ProviderConfigError. There is no silent
fallback to a different provider, because that would change the provenance of results.
"""
from __future__ import annotations

from typing import Optional

from core.config import PROVIDERS, Settings

from .anthropic import AnthropicProvider
from .base import Provider, ProviderConfigError, Transport
from .gemini import GeminiProvider
from .local import LocalProvider
from .openai import OpenAIProvider

_REMOTE = {"openai": OpenAIProvider, "gemini": GeminiProvider, "anthropic": AnthropicProvider}


def get_provider(settings: Settings, name: Optional[str] = None, transport: Optional[Transport] = None) -> Provider:
    name = name or settings.ai_provider
    if name not in PROVIDERS:
        raise ProviderConfigError(f"unknown provider '{name}'")
    if name == "local":
        return LocalProvider()
    return _REMOTE[name](settings.api_key_for(name), transport=transport, timeout=settings.ai_timeout_seconds,
                         max_retries=settings.ai_max_retries, requests_per_minute=settings.ai_requests_per_minute)


def provider_status(settings: Settings) -> list:
    """Configuration status only. Never includes key material."""
    out = [{"name": "local", "configured": True, "default": settings.ai_provider == "local",
            "provenance": "computation", "note": "deterministic, offline, no API key"}]
    for n in ("openai", "gemini", "anthropic"):
        out.append({"name": n, "configured": bool(settings.api_key_for(n)), "default": settings.ai_provider == n,
                    "provenance": "ai_hypothesis", "note": "optional; output is labelled ai_hypothesis"})
    return out
