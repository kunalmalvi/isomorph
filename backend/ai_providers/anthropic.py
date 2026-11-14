"""Anthropic messages adapter (written to the public API spec, exercised only with a mocked transport)."""
from __future__ import annotations

from .base import CompletionRequest, HttpProvider, ProviderSchemaError


class AnthropicProvider(HttpProvider):
    name = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"
    default_model = "claude-3-5-haiku-latest"

    def headers(self):
        return {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}

    def build_body(self, req: CompletionRequest) -> dict:
        body = {"model": self.model, "max_tokens": req.max_tokens, "temperature": req.temperature,
                "messages": [{"role": "user", "content": self._prompt(req)}]}
        if req.system:
            body["system"] = req.system
        return body

    def parse_response(self, data):
        try:
            parts = [b["text"] for b in data["content"] if b.get("type") == "text"]
        except (KeyError, TypeError):
            raise ProviderSchemaError("unexpected Anthropic response shape")
        text = "".join(parts)
        if not text.strip():
            raise ProviderSchemaError("empty Anthropic response")
        u = data.get("usage") or {}
        return text, {"prompt_tokens": int(u.get("input_tokens", 0)), "completion_tokens": int(u.get("output_tokens", 0))}
