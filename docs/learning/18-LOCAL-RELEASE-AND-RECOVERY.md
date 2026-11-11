# Local release and recovery

## What this milestone means

FlowForge runs locally with Next.js, FastAPI, PostgreSQL, Redis and Celery. It supports accounts/workspaces, provider-backed agents, bounded DAG workflows, tools, MCP, webhooks/schedules, deployment endpoints, templates, execution inspection and shared usage controls. The [phase table](../DEVELOPMENT_PHASES.md) retains unfinished advanced orchestration and public-service work. This milestone does not certify an n8n-scale connector ecosystem or production operations.

## Start and check

With Docker Desktop running, from the project root:

```powershell
python scripts/init-env.py
docker compose up -d --build
```

Open http://localhost:8080 and create your own account. No shared password is installed. Development email appears in http://localhost:8025. Connect your provider key through Integrations, not through chat or instructions. Existing keys and data are preserved by the initializer and additive migrations. To stop without deleting data, use `docker compose stop`.

`/health/live` checks the API process; `/health/ready` checks PostgreSQL, the installed migration and Redis. Neither endpoint alone proves that Celery workers are processing tasks. The integration suite starts a fresh Celery process and completes a DAG through real Redis/PostgreSQL to verify that path.

The standard local topology uses the Next.js Webpack development server with polling for ongoing editing. Polling is needed here because native change events from Windows-mounted source did not consistently refresh the rendered app. A production Webpack build is also checked. Public hosting, HTTPS termination, subscriptions, external email delivery and real upstream acceptance are separate from a local pass.

## Repeat the release checks

```powershell
docker compose --profile test run --rm --build tests
docker compose --profile test run --rm tests ruff check app tests migrations scripts
docker compose --profile test run --rm tests python scripts/export_openapi.py --check
cd frontend
npm run lint
npm run typecheck
npm test
npm run api:check
npm run build
```

Integration tests refuse to reset a database without a `_test` suffix. Never change that guard or point tests at the live database. `scripts/smoke.mjs` additionally checks real same-origin pages using a disposable account; its cleanup script removes temporary mutable data/sessions while preserving identities referenced by immutable audit records. It does not establish visual accessibility compliance or live upstream acceptance.

## Encrypted backup

The database contains encrypted credentials and execution payloads. The separate credential master key is necessary to decrypt them. Backing up only PostgreSQL is insufficient. The local backup command packages the custom-format PostgreSQL dump, `.env` and credential key inside an authenticated, password-encrypted envelope. It uses AES-256-GCM, a fresh salt/nonce and scrypt key derivation; no plaintext dump or key is written to the backup directory. ZIP entries are read in memory and never extracted to arbitrary paths.

From the project root, using the existing backend Python environment:

```powershell
backend\.venv\Scripts\python.exe scripts/local-backup.py create .local/backups/flowforge-local.ffbackup
```

Enter a password of at least sixteen characters at the private prompt. The file will not overwrite an existing backup. Keep the password separately in a password manager and copy the encrypted file to an independent device/location. Losing both the live master key and the backup password prevents recovery. Restrict local filesystem access; Windows ACLs should protect the workspace and `.env`. Do not commit backups or passwords.

For a quiet snapshot, stop `api`, `frontend`, `agent-worker` and `maintenance` first, leaving PostgreSQL running. Repeat capture if keys/environment change during dumping. PostgreSQL supplies a consistent database snapshot, but this small local tool is not an online master-key rotation protocol or point-in-time recovery system. It has a 256 MiB payload limit and uses memory for encryption; move to managed backup/WAL tooling as data grows. A failed write can leave an incomplete output file; verification rejects it.

## Rehearse a restore safely

```powershell
backend\.venv\Scripts\python.exe scripts/local-backup.py verify .local/backups/flowforge-local.ffbackup
```

This unlocks the bundle and checks authenticated integrity, file hashes and the credential-key length. It creates a random temporary PostgreSQL database, restores the dump with errors fatal, checks migration metadata and required tables, then drops only that database. No workers use the restored database, so schedules/actions cannot execute. It never replaces live data, environment or keys.

The development command below performs the same capture/encryption/restore exercise using a transient password held in memory. It saves no durable backup, so it is evidence of recoverability rather than a substitute for making your own backup:

```powershell
backend\.venv\Scripts\python.exe scripts/local-backup.py rehearse
```

The rehearsal passed against the local migration-0021 database. The live installation remained running and no user records or credentials were displayed. A real disaster recovery procedure must restore into an isolated installation first, recreate database roles using the saved environment, install the matching credential key, revoke old sessions/deployment keys as appropriate, and inspect pending runs/automations before allowing workers to start. Live replacement is deliberately excluded from this helper.

## Why these choices

A tested, explicit local backup is useful now and avoids introducing cloud infrastructure solely for development. Password-based encryption makes the artifact portable while keeping its recovery secret separate. A disposable restore proves more than merely checking that a dump command returned success. Managed encrypted snapshots and WAL archiving are preferable when retention, size, recovery-time or point-in-time requirements demand them.

For public service, add operator-owned plan ceilings, master-key rotation, monitored worker heartbeats, alerting, load/capacity isolation, outbound network policy and external security review. The current logs carry request IDs and execution metadata; customer payloads and secrets must stay out of logs. Do not treat local workspace-admin quotas as subscription enforcement.
