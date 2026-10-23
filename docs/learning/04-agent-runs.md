# Lesson 4: A published agent becomes a durable run

This phase connects a frozen, published agent version to one real model call. The first adapters run OpenAI GPT-5 Mini and Gemini 2.5 Flash with JSON input and JSON output. OpenRouter, Claude and DeepSeek remain useful for configuration and publishing; their live execution adapters are still to come.

## Follow one run

1. In Integrations, an owner or admin connects an OpenAI key. The key is verified, encrypted, and never returned to the browser.
2. An editor configures an agent, saves it, and publishes a version. That version freezes instructions, model, schemas, limits and the credential generation.
3. On the version history screen, **Run agent** opens Runs with the published snapshot selected. JSON input is checked against its schema before the run is accepted. The request needs an idempotency key; replaying the same key and body returns the original run.
4. PostgreSQL commits a queued run and encrypted input. A maintenance process sends its ID through Redis to a Celery worker. The worker claims it with a database lock, checks the pinned credential generation, and records a marker immediately before the provider request.
5. The worker sends one bounded request to the selected provider's fixed API host with a JSON-schema output format and a maximum output-token count. OpenAI requests set `store: false`; Gemini 2.5 Flash requests disable thinking to reserve output tokens for the answer. It validates the response again locally, stores encrypted output and measured usage, then marks the run complete.
6. The Runs screen polls while work is active and displays output, failure, token use and cost. Cancellation before the provider marker prevents the call. After the marker, cancellation stops presenting a successful outcome but cannot guarantee the provider will stop charging.

## Why these decisions

PostgreSQL owns state because Redis delivery can be duplicated or lost. The maintenance process requeues a stale worker claim only if the provider-call marker was never written. Once a call may have begun, retrying automatically could make a second charge; the run eventually expires with an uncertain-cost indicator. This is an explicit reliability tradeoff: occasional manual review is preferable to hidden duplicate calls.

The per-run reservation uses an intentionally conservative input-token estimate plus a capped output allowance. It is a guardrail, not a guaranteed ceiling: actual tokenization, provider behavior and pricing can differ. Model pricing and request parameters should be reviewed against the [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5-mini), [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [Gemini Generate Content API](https://ai.google.dev/api/generate-content) before production use.

Input, output and credentials use AES-256-GCM with workspace-bound associated data. Database readers do not receive plaintext merely by viewing a row. Application authorization still decides who may submit or view a run. The API returns at most the recent 50 runs; pagination and retention policy are future work.

## How to verify it

The backend tests exercise duplicate submissions, encrypted storage, completion with a mocked provider, cancellation, uncertain outcomes, tenant isolation and a pre-call worker crash. The mock avoids charges and keeps CI deterministic. The frontend is checked by lint, TypeScript and an isolated production build. A real key and real provider request are intentionally not part of automated tests.

Next we will add one adapter at a time for OpenRouter, Claude and DeepSeek. Each adapter must define its own request shape, structured-output behavior, failure classification and usage mapping before live runs are enabled for that model.
