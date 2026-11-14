# AI Integration Rules
- Default mode is deterministic local with no LLM. The platform must be fully usable without any external provider.
- All providers implement one interface in backend/ai_providers. Providers are swappable by configuration.
- AI output is always tagged ai_hypothesis and is never written into source or computation fields.
- Prompts and responses are logged in activity logs with provider name and model, excluding secrets.
- Validate AI output against schemas. On invalid output, discard and report; never repair silently.
- API keys come from environment variables only.
- Never present AI output as validated fact.

## Concrete rules from the code (phase 3)
- Providers are `local`, `openai`, `gemini`, `anthropic`, chosen by `AI_PROVIDER` (backend/core/config.py). Any other value fails settings validation.
- A remote provider without a key raises. It never falls back to local silently (tests/platform/test_ai_providers.py::test_remote_without_key_raises_not_falls_back).
- The local provider refuses tasks it cannot do instead of inventing output.
- Provider output is validated against a schema. A schema violation raises and is not retried. Retries apply only to 429, 5xx and timeouts, with backoff; other HTTP errors fail fast. Defaults: `AI_TIMEOUT_SECONDS=30`, `AI_MAX_RETRIES=2`, `AI_REQUESTS_PER_MINUTE=30`.
- Provider status endpoints expose no key material.
- Only the perception stage can use a remote provider. Later stages are deterministic engine code.
- The OpenAI, Gemini and Anthropic adapters were tested only against a mocked transport. Treat real calls as UNVERIFIED.
- Uploaded PDFs and images are never sent to a provider or read. They are stored and flagged `interpreted=false`.
