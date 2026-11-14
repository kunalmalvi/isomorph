"""Deterministic local provider. No network, no API key, same input gives the same output.

It supports only tasks the rule based engine can really perform. Anything else raises ProviderUnsupported;
it does not pretend to be a language model.
"""
from __future__ import annotations

import re

from intelligence.perception import perceive_text

from .base import (CompletionRequest, CompletionResult, Provider, ProviderSchemaError, ProviderUnsupported,
                   validate_schema)

SUPPORTED_TASKS = ("extract_structure", "summarize")
_SENT = re.compile(r"(?<=[.!?])\s+")


class LocalProvider(Provider):
    name = "local"
    provenance = "computation"
    model = "isomorph-rules-v1"

    def complete(self, req: CompletionRequest) -> CompletionResult:
        if req.task == "extract_structure":
            parsed = perceive_text(req.prompt, req.system or "").to_dict()
            text = None
        elif req.task == "summarize":
            sents = [s.strip() for s in _SENT.split(req.prompt.strip()) if s.strip()]
            n = max(1, min(3, len(sents)))
            parsed = {"summary": " ".join(sents[:n]), "method": "first sentences (extractive)"}
        else:
            self.usage.record_failure(1)
            raise ProviderUnsupported(f"local provider does not support task '{req.task}'. Supported: {', '.join(SUPPORTED_TASKS)}")
        if req.schema is not None:
            errs = validate_schema(parsed, req.schema)
            if errs:
                self.usage.record_failure(1)
                raise ProviderSchemaError("; ".join(errs[:5]))
        import json
        text = json.dumps(parsed, sort_keys=True)
        self.usage.record_success({"prompt_tokens": 0, "completion_tokens": 0}, 1)
        return CompletionResult(text, parsed, self.name, self.model, self.provenance, {}, 1)
