# AI Integration Rules
- Default mode is deterministic local with no LLM. The platform must be fully usable without any external provider.
- All providers implement one interface in backend/ai_providers. Providers are swappable by configuration.
- AI output is always tagged ai_hypothesis and is never written into source or computation fields.
- Prompts and responses are logged in activity logs with provider name and model, excluding secrets.
- Validate AI output against schemas. On invalid output, discard and report; never repair silently.
- API keys come from environment variables only.
- Never present AI output as validated fact.
