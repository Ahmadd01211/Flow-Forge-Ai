# Provider connection and agent publication

Implemented 20 October 2026 and expanded to five providers. Connections do not submit generation requests or charge for model output.

## Follow the credential

An owner or admin enters a key in Integrations. The existing session, Origin and CSRF checks protect the request. FlowForge verifies it against a fixed HTTPS endpoint for OpenAI, OpenRouter, Claude, Gemini or DeepSeek. It lists models with short timeouts, no redirects, no environment proxy and a bounded response. OpenRouter first checks its authenticated [current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key), because its [model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models) can be public. Other model endpoints follow the providers' [Claude](https://platform.claude.com/docs/en/api/models/list), [Gemini](https://ai.google.dev/api/models), and [DeepSeek](https://api-docs.deepseek.com/api/list-models/) references. A successful check shows access at that moment, not billing capacity or successful generation.

The server encrypts the key with AES-256-GCM before inserting it into PostgreSQL. The 32-byte master key lives in an ignored local file mounted read-only into backend containers, separate from database backups. A fresh random nonce and workspace/connection/generation associated data bind each ciphertext to its owner. API responses show only a short masked hint. The key never appears in agent JSON, audit details or HTTP responses. Rotate verifies the new key before replacing the old encrypted record; revoke deletes the stored ciphertext and blocks new publication. Database backups made before rotation can still contain prior ciphertext, so backup retention and master-key rotation need a production policy.

## Follow Publish version

The editor first saves a draft with both provider and model ID. Publish sends the expected draft revision and optional change summary, not a client-supplied frozen definition. FastAPI locks the draft, checks that provider's active connection and listed model, and revalidates the saved JSON Schemas. For OpenAI GPT-5 Mini it also checks a narrow Structured Outputs profile. It then inserts a published `agent_version` and audit event in the same transaction. A repeat request for the same revision returns the existing version. The published row pins the connection ID **and credential generation** and remains immutable; revoking or rotating the connection does not rewrite history. The future runner must require that the pinned generation is still active before any call.

For the GPT-5 Mini profile, each output object must forbid extra properties and require every declared field. Those rules follow the [official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs). Other providers receive local schema validation; their native structured-output capabilities will be handled by execution adapters. We still have no runtime call, cost ledger or tool grant mechanism, so publication means a validated definition ready for the next execution slice.

## Why fixed provider endpoints?

An arbitrary URL paired with an API key would let a malicious caller direct server traffic to internal addresses or leak credentials. The five supported provider profiles use fixed upstream hosts and provider-specific authentication. A future custom OpenAI-compatible endpoint needs a hardened outbound proxy with DNS and IP controls before it can safely be enabled. Tests use deterministic substitutes and make no paid or external API requests.

## Try it

Open **Integrations** as a workspace owner or admin. In the single setup panel, select a provider, verify its key, search the returned model list, and save a default model. The compact provider list lets you switch between connections. A new agent starts with the saved default; its **Model & tools** tab can choose another listed model. Rotation or revocation affects only that provider. Do not put credentials in repository files, screenshots, or chat messages.
