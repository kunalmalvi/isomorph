"""Google Gemini generateContent adapter (written to the public API spec, exercised only with a mocked transport)."""
from __future__ import annotations

from .base import CompletionRequest, HttpProvider, ProviderSchemaError


class GeminiProvider(HttpProvider):
    name = "gemini"
    default_model = "gemini-1.5-flash"

    def url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def headers(self):
        return {"x-goog-api-key": self._api_key}

    def build_body(self, req: CompletionRequest) -> dict:
        cfg = {"temperature": req.temperature, "maxOutputTokens": req.max_tokens}
        if req.schema:
            cfg["responseMimeType"] = "application/json"
        body = {"contents": [{"role": "user", "parts": [{"text": self._prompt(req)}]}], "generationConfig": cfg}
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        return body

    def parse_response(self, data):
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise ProviderSchemaError("unexpected Gemini response shape (possibly blocked or empty)")
        if not text.strip():
            raise ProviderSchemaError("empty Gemini response")
        u = data.get("usageMetadata") or {}
        return text, {"prompt_tokens": int(u.get("promptTokenCount", 0)), "completion_tokens": int(u.get("candidatesTokenCount", 0))}
