import json

import pytest

from ai_providers import (CompletionRequest, LocalProvider, ProviderConfigError, ProviderHTTPError, ProviderSchemaError,
                          ProviderUnsupported, Transport, get_provider, provider_status, validate_schema)
from ai_providers.anthropic import AnthropicProvider
from ai_providers.base import ProviderRateLimited, ProviderTransportError
from ai_providers.gemini import GeminiProvider
from ai_providers.openai import OpenAIProvider
from core.config import load_settings

SCHEMA = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}, "n": {"type": "integer", "minimum": 0}}}


class FakeTransport(Transport):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def openai_ok(text):
    return 200, {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}


def make(cls, transport, **kw):
    return cls("key-123", transport=transport, sleep=lambda s: None, **kw)


def test_local_default_no_key_and_deterministic():
    p = get_provider(load_settings({}))
    assert isinstance(p, LocalProvider)
    r = CompletionRequest("A pump moves water. The tank stores water.", task="extract_structure")
    a, b = p.complete(r), p.complete(r)
    assert a.text == b.text and a.provenance == "computation" and "problem" in a.parsed


def test_local_refuses_unsupported_task_instead_of_fabricating():
    with pytest.raises(ProviderUnsupported):
        LocalProvider().complete(CompletionRequest("write a poem", task="creative"))


def test_local_summarize():
    r = LocalProvider().complete(CompletionRequest("One. Two. Three. Four.", task="summarize"))
    assert r.parsed["summary"] == "One. Two. Three."


def test_remote_without_key_raises_not_falls_back():
    with pytest.raises(ProviderConfigError):
        get_provider(load_settings({}), "openai")
    with pytest.raises(ProviderConfigError):
        get_provider(load_settings({}), "bogus")


def test_provider_status_has_no_key_material():
    s = load_settings({"OPENAI_API_KEY": "sk-secret-value", "AI_PROVIDER": "openai"})
    st = provider_status(s)
    assert "sk-secret-value" not in json.dumps(st)
    assert {x["name"]: x["configured"] for x in st} == {"local": True, "openai": True, "gemini": False, "anthropic": False}


def test_openai_request_shape_and_structured_output():
    t = FakeTransport([openai_ok('{"answer": "yes", "n": 2}')])
    p = make(OpenAIProvider, t)
    res = p.complete(CompletionRequest("q", system="sys", schema=SCHEMA))
    url, headers, body, timeout = t.calls[0]
    assert url.startswith("https://api.openai.com/") and headers["Authorization"] == "Bearer key-123"
    assert body["messages"][0] == {"role": "system", "content": "sys"} and body["response_format"]["type"] == "json_object"
    assert res.parsed == {"answer": "yes", "n": 2} and res.provenance == "ai_hypothesis"
    assert res.usage == {"prompt_tokens": 7, "completion_tokens": 3}
    assert p.usage.snapshot()["prompt_tokens"] == 7


def test_fenced_json_is_accepted():
    p = make(OpenAIProvider, FakeTransport([openai_ok('```json\n{"answer": "x"}\n```')]))
    assert p.complete(CompletionRequest("q", schema=SCHEMA)).parsed == {"answer": "x"}


@pytest.mark.parametrize("text", ["not json", '{"n": 1}', '{"answer": 5}', '{"answer": "a", "n": -1}', "[]"])
def test_schema_violation_raises_and_is_not_retried(text):
    t = FakeTransport([openai_ok(text), openai_ok('{"answer": "late"}')])
    p = make(OpenAIProvider, t)
    with pytest.raises(ProviderSchemaError):
        p.complete(CompletionRequest("q", schema=SCHEMA))
    assert len(t.calls) == 1
    assert p.usage.snapshot()["failures"] == 1


def test_retry_on_429_then_success_and_backoff():
    sleeps = []
    t = FakeTransport([(429, {"error": {"message": "slow down"}}), (503, {}), openai_ok("hi")])
    p = OpenAIProvider("k", transport=t, sleep=sleeps.append, max_retries=2, backoff=0.5)
    r = p.complete(CompletionRequest("q"))
    assert r.text == "hi" and r.attempts == 3 and sleeps == [0.5, 1.0]
    assert p.usage.snapshot()["retries"] == 2


def test_retries_exhausted_raises_last_error():
    t = FakeTransport([(500, {})] * 3)
    p = make(OpenAIProvider, t, max_retries=2)
    with pytest.raises(ProviderHTTPError) as ei:
        p.complete(CompletionRequest("q"))
    assert ei.value.status == 500 and len(t.calls) == 3


def test_non_retryable_http_error_fails_fast():
    t = FakeTransport([(401, {"error": {"message": "bad key"}})])
    with pytest.raises(ProviderHTTPError, match="bad key"):
        make(OpenAIProvider, t).complete(CompletionRequest("q"))
    assert len(t.calls) == 1


def test_transport_timeout_is_retried_then_raised():
    t = FakeTransport([ProviderTransportError("timeout")] * 2)
    p = make(OpenAIProvider, t, max_retries=1)
    with pytest.raises(ProviderTransportError):
        p.complete(CompletionRequest("q"))
    assert len(t.calls) == 2


def test_local_rate_limit():
    t = FakeTransport([openai_ok("a"), openai_ok("b")])
    p = make(OpenAIProvider, t, requests_per_minute=1)
    p.complete(CompletionRequest("q"))
    with pytest.raises(ProviderRateLimited):
        p.complete(CompletionRequest("q"))
    assert len(t.calls) == 1


def test_anthropic_adapter():
    t = FakeTransport([(200, {"content": [{"type": "text", "text": '{"answer":"a"}'}], "usage": {"input_tokens": 4, "output_tokens": 2}})])
    r = make(AnthropicProvider, t).complete(CompletionRequest("q", system="s", schema=SCHEMA))
    url, headers, body, _ = t.calls[0]
    assert headers["x-api-key"] == "key-123" and "anthropic-version" in headers and body["system"] == "s"
    assert r.parsed == {"answer": "a"} and r.usage == {"prompt_tokens": 4, "completion_tokens": 2}


def test_gemini_adapter_and_empty_response():
    t = FakeTransport([(200, {"candidates": [{"content": {"parts": [{"text": '{"answer":"g"}'}]}}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1}}),
                       (200, {"candidates": []})])
    p = make(GeminiProvider, t)
    r = p.complete(CompletionRequest("q", schema=SCHEMA))
    assert "generateContent" in t.calls[0][0] and t.calls[0][1]["x-goog-api-key"] == "key-123"
    assert "key-123" not in t.calls[0][0]
    assert r.usage["prompt_tokens"] == 5
    with pytest.raises(ProviderSchemaError):
        p.complete(CompletionRequest("q"))


def test_malformed_provider_response_shape_raises():
    with pytest.raises(ProviderSchemaError):
        make(OpenAIProvider, FakeTransport([(200, {"nothing": 1})])).complete(CompletionRequest("q"))


def test_validate_schema_basics():
    assert validate_schema({"answer": "x"}, SCHEMA) == []
    assert validate_schema(True, {"type": "integer"})
    assert validate_schema([1, "a"], {"type": "array", "items": {"type": "integer"}, "minItems": 1})
    assert validate_schema("z", {"enum": ["a"]})
