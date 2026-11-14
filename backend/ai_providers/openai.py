"""OpenAI chat completions adapter (written to the public API spec, exercised only with a mocked transport)."""
from __future__ import annotations

from .base import CompletionRequest, HttpProvider, ProviderSchemaError


class OpenAIProvider(HttpProvider):
    name = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"
    default_model = "gpt-4o-mini"

    def headers(self):
        return {"Authorization": f"Bearer {self._api_key}"}

    def build_body(self, req: CompletionRequest) -> dict:
        msgs = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        msgs.append({"role": "user", "content": self._prompt(req)})
        body = {"model": self.model, "messages": msgs, "temperature": req.temperature, "max_tokens": req.max_tokens}
        if req.schema:
            body["response_format"] = {"type": "json_object"}
        return body

    def parse_response(self, data):
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderSchemaError("unexpected OpenAI response shape")
        if not isinstance(text, str) or not text.strip():
            raise ProviderSchemaError("empty OpenAI response")
        u = data.get("usage") or {}
        return text, {"prompt_tokens": int(u.get("prompt_tokens", 0)), "completion_tokens": int(u.get("completion_tokens", 0))}
