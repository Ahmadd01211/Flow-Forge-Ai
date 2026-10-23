# Phase 3: provider connections and execution capabilities

## What this phase delivers

The workspace can connect separate encrypted keys for OpenAI, OpenRouter, Claude, Gemini and DeepSeek. The same setup component selects a provider, verifies a key, searches its model catalog, explains execution support, and saves a default model. Admins can refresh a catalog using the encrypted saved key without supplying it again or changing its generation. Rotation/revocation remains a separate action.

The backend is the source of truth for execution profiles and standard text pricing. Each connection response includes `model_capabilities`, keyed by the exact provider model ID. Agent Builder and version history consume those fields instead of maintaining their own hard-coded lists. The intersection of a reviewed profile and the provider's saved listing determines the available execution capabilities. No billed inference call is made during connection or refresh.

## Supported local scope

| Provider | Reviewed model IDs | FlowForge local tools |
|---|---|---|
| OpenAI | gpt-5-mini, gpt-5-nano, gpt-5 | Yes, through the bounded Responses tool loop |
| Gemini | gemini-2.5-flash, gemini-2.5-flash-lite | No |
| Claude | claude-haiku-4-5, claude-haiku-4-5-20251001, claude-sonnet-4-6 | No |
| DeepSeek | deepseek-flash, deepseek-v4-pro | No |
| OpenRouter | openai/gpt-4o-mini | No |

These are text-input/JSON-output profiles, not claims about every feature a provider's model supports. Provider-native images, audio and tools are outside this phase. Agent tool support for other providers belongs to phase 5. User-supplied upstream URLs and arbitrary credentials for other services belong to the later secured connector phase.

Other listed models remain visible under **Show models for setup only**. Users can preserve draft/version definitions for them, but the runtime refuses execution until a reviewed adapter and pricing profile exist. A saved default also does not promise execution support. Refreshing a catalog that removes a model clears that default and blocks new runs of that model. Publication freezes the definition, while current provider access is checked at submission and worker start.

## Why explicit profiles

Model listing endpoints can include embedding, realtime, image or otherwise incompatible models. Inferring execution support from a model's name would allow invalid requests and misleading budget estimates. Explicit profiles make the limited support auditable. The alternative is a provider capability/price discovery protocol backed by compatibility tests; reconsider when connector breadth justifies that infrastructure. No silent model substitutions or automatic credential rotations occur.

Catalog paging uses fixed destinations, encoded cursors and bounded bytes, pages, model count and total elapsed time. An upstream-supplied URL never receives a key. Invalid or incomplete pagination fails the refresh and preserves the saved catalog. Refresh and connect are owner/admin-only, require CSRF, and share a rate limit. A failed refresh preserves credential generation, ciphertext, model list and default.

## Pricing and official contracts

Rates are estimates for standard uncached text, not a billing guarantee. DeepSeek profiles use peak rates. Reasoning output remains part of output-token usage. Provider credits, geographic multipliers, negotiated prices, aliases and retirement dates can change; review profiles before production. GPT-5 and GPT-5 Nano are legacy/deprecated profiles in the current OpenAI catalog, retained for users whose provider still lists them; they are not recommendations for a new model migration.

References checked on 23 October 2026:

- [OpenAI GPT-5 Nano](https://developers.openai.com/api/docs/models/gpt-5-nano), [GPT-5](https://developers.openai.com/api/docs/models/gpt-5), and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
- [Google Gemini standard pricing](https://ai.google.dev/gemini-api/docs/pricing) and [Flash-Lite capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite).
- [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) and [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/).
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs) and [GPT-4o Mini](https://openrouter.ai/openai/gpt-4o-mini).

## What the tests prove

Mock HTTP contracts exercise every reviewed model ID through its fixed upstream host and expected request/response format. PostgreSQL tests exercise publication, run submission, worker completion and cost recording for the four new profiles; the existing local-tool loop tests cover each reviewed OpenAI model. Refresh tests cover preservation of encryption/generation, failed-refresh atomicity, removed-model denial, CSRF, editor denial and tenant isolation. Pagination tests cover both supported cursor protocols, hostile cursor strings and repeated cursors.

No paid provider call or real customer key is used. A catalog listing is not proof of generation entitlement, available credit, model availability at execution time, or provider-side schema acceptance for every possible schema. Those failures remain visible in run diagnostics.
