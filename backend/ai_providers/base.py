"""AI provider abstraction. Stdlib only.

Rules:
- A provider call either returns a validated result or raises. It never returns invented content.
- Results from remote models carry provenance "ai_hypothesis"; the local provider reports "computation".
- Transient failures (timeouts, 429, 5xx) are retried with backoff up to `max_retries`; then the error is raised.
- Structured output is validated against a JSON schema subset. Invalid output raises ProviderSchemaError.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.rate_limit import RateLimiter


class ProviderError(Exception):
    """Base error. `retryable` tells callers whether another attempt may succeed."""
    retryable = False


class ProviderConfigError(ProviderError):
    """Missing key or unknown provider. Never falls back to another provider."""


class ProviderUnsupported(ProviderError):
    """The provider cannot do the requested task."""


class ProviderTransportError(ProviderError):
    retryable = True


class ProviderHTTPError(ProviderError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.retryable = status == 429 or status >= 500


class ProviderRateLimited(ProviderError):
    retryable = False

    def __init__(self, retry_after: float):
        super().__init__(f"local rate limit reached, retry after {retry_after:.1f}s")
        self.retry_after = retry_after


class ProviderSchemaError(ProviderError):
    """Model output was not valid JSON or did not match the schema."""


@dataclass
class CompletionRequest:
    prompt: str
    task: str = "generic"
    system: Optional[str] = None
    schema: Optional[dict] = None
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class CompletionResult:
    text: str
    parsed: Optional[Any]
    provider: str
    model: str
    provenance: str
    usage: Dict[str, int] = field(default_factory=dict)
    attempts: int = 1

    def to_dict(self) -> dict:
        return {"text": self.text, "parsed": self.parsed, "provider": self.provider, "model": self.model,
                "provenance": self.provenance, "usage": self.usage, "attempts": self.attempts}


class UsageTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.requests = 0
        self.failures = 0
        self.retries = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def record_success(self, usage: Dict[str, int], attempts: int) -> None:
        with self._lock:
            self.requests += 1
            self.retries += max(0, attempts - 1)
            self.prompt_tokens += int(usage.get("prompt_tokens", 0))
            self.completion_tokens += int(usage.get("completion_tokens", 0))

    def record_failure(self, attempts: int) -> None:
        with self._lock:
            self.requests += 1
            self.failures += 1
            self.retries += max(0, attempts - 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {"requests": self.requests, "failures": self.failures, "retries": self.retries,
                    "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


# ------------------------------------------------------------------ schema validation
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def validate_schema(data: Any, schema: dict, path: str = "$") -> List[str]:
    """Validate a JSON schema subset: type, required, properties, items, enum, minimum, maximum, minItems."""
    errs: List[str] = []
    t = schema.get("type")
    if t:
        if t == "number":
            ok = isinstance(data, (int, float)) and not isinstance(data, bool)
        elif t == "integer":
            ok = isinstance(data, int) and not isinstance(data, bool)
        else:
            ok = isinstance(data, _TYPES[t])
        if not ok:
            return [f"{path}: expected {t}, got {type(data).__name__}"]
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: {data!r} not in {schema['enum']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}: {data} below minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errs.append(f"{path}: {data} above maximum {schema['maximum']}")
    if isinstance(data, dict):
        for k in schema.get("required", []):
            if k not in data:
                errs.append(f"{path}: missing required '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                errs += validate_schema(data[k], sub, f"{path}.{k}")
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, x in enumerate(data):
                errs += validate_schema(x, schema["items"], f"{path}[{i}]")
    return errs


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


def parse_json_text(text: str) -> Any:
    s = text.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1)
    try:
        return json.loads(s)
    except ValueError as e:
        raise ProviderSchemaError(f"model output is not valid JSON: {e}")


# ------------------------------------------------------------------ transport
class Transport:
    """HTTP transport interface. Tests inject a fake; production uses UrllibTransport."""

    def post_json(self, url: str, headers: Dict[str, str], body: dict, timeout: float) -> Tuple[int, dict]:
        raise NotImplementedError


class UrllibTransport(Transport):
    def post_json(self, url, headers, body, timeout):
        if not url.startswith("https://"):
            raise ProviderConfigError("only https endpoints are allowed")
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https enforced above)
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ProviderTransportError(f"network error: {e}")
        except ValueError as e:
            raise ProviderTransportError(f"invalid response body: {e}")


# ------------------------------------------------------------------ providers
class Provider:
    name = "base"
    provenance = "ai_hypothesis"
    model = ""

    def __init__(self):
        self.usage = UsageTracker()

    def complete(self, req: CompletionRequest) -> CompletionResult:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "model": self.model, "provenance": self.provenance, "usage": self.usage.snapshot()}

    def describe_image(self, data: bytes, media_type: str) -> str:
        """Text description of an image. No adapter implements vision yet, so this always raises rather than inventing."""
        raise ProviderUnsupported(f"provider '{self.name}' does not support image input")


class HttpProvider(Provider):
    """Shared retry, rate limit, usage tracking and schema validation for remote adapters."""
    endpoint = ""
    default_model = ""

    def __init__(self, api_key: Optional[str], model: Optional[str] = None, transport: Optional[Transport] = None,
                 timeout: float = 30.0, max_retries: int = 2, requests_per_minute: int = 30,
                 sleep: Callable[[float], None] = time.sleep, backoff: float = 0.5,
                 limiter: Optional[RateLimiter] = None):
        super().__init__()
        if not api_key:
            raise ProviderConfigError(f"{self.name}: API key is not configured")
        self._api_key = api_key
        self.model = model or self.default_model
        self.transport = transport or UrllibTransport()
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.sleep = sleep
        self.backoff = backoff
        self.limiter = limiter or RateLimiter(requests_per_minute, 60.0)

    # adapters implement these three
    def url(self) -> str:
        return self.endpoint

    def headers(self) -> Dict[str, str]:
        raise NotImplementedError

    def build_body(self, req: CompletionRequest) -> dict:
        raise NotImplementedError

    def parse_response(self, data: dict) -> Tuple[str, Dict[str, int]]:
        raise NotImplementedError

    def _prompt(self, req: CompletionRequest) -> str:
        if req.schema:
            return req.prompt + "\n\nRespond with a single JSON object that matches this JSON schema and nothing else:\n" + \
                json.dumps(req.schema, sort_keys=True)
        return req.prompt

    def complete(self, req: CompletionRequest) -> CompletionResult:
        allowed, retry_after = self.limiter.check(self.name)
        if not allowed:
            raise ProviderRateLimited(retry_after)
        attempts = 0
        last: Optional[ProviderError] = None
        while attempts <= self.max_retries:
            attempts += 1
            try:
                status, data = self.transport.post_json(self.url(), self.headers(), self.build_body(req), self.timeout)
                if status != 200:
                    msg = (data.get("error", {}) or {}).get("message") if isinstance(data.get("error"), dict) else None
                    raise ProviderHTTPError(status, msg or "request failed")
                text, usage = self.parse_response(data)
                parsed = None
                if req.schema is not None:
                    parsed = parse_json_text(text)
                    errs = validate_schema(parsed, req.schema)
                    if errs:
                        raise ProviderSchemaError("; ".join(errs[:5]))
                self.usage.record_success(usage, attempts)
                return CompletionResult(text, parsed, self.name, self.model, self.provenance, usage, attempts)
            except ProviderError as e:
                last = e
                if not e.retryable or attempts > self.max_retries:
                    break
                self.sleep(self.backoff * (2 ** (attempts - 1)))
        self.usage.record_failure(attempts)
        assert last is not None
        raise last
