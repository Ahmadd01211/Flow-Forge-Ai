# Agent snapshots and contract testing

Implemented 20 October 2026. This slice freezes saved configuration and checks example data; it does not run a model.

## Three different things

- **Draft revision:** editable work in progress. Save increments its revision.
- **Immutable snapshot:** a frozen name, description, instructions, schemas and limits, linked to the exact saved revision and creator.
- **Execution run:** a later record of doing work with a pinned snapshot. No execution run is created by contract validation.

This distinction matters because editing an agent tomorrow must not alter the definition used by yesterday's test or future workflow version.

## Follow Create snapshot

The browser requires a saved draft and instructions. It sends expected_revision, not an editable version body. FastAPI checks session/CSRF/workspace authority, locks the agent and checks that revision. The service validates the stored schemas, allocates the next version number and stores a copy plus an audit event in one transaction. Repeated or concurrent requests for the same revision return the same existing snapshot; the first change summary remains authoritative.

The transaction lock serializes version numbering. Uniqueness constraints backstop concurrent mistakes. A composite workspace/agent foreign key prevents a snapshot from referring to another workspace's agent. Tests cover all three properties with real PostgreSQL.

## Why database immutability too?

Hiding edit/delete endpoints is useful, but a later maintenance script could still change a row. PostgreSQL triggers reject UPDATE/DELETE, and the application role receives SELECT/INSERT only for snapshots and audit records. Privileged database administrators can still change the schema/disable protections: this is application integrity, not an assertion that database administrators have no power. [PostgreSQL trigger behavior](https://www.postgresql.org/docs/current/sql-createtrigger.html).

Restore copies a selected snapshot into the mutable draft and increments its revision, after an explicit UI confirmation. The old snapshot is not rewritten. A stale restore receives a conflict. Version history compares the snapshot to the **saved** draft and explains when unsaved changes are excluded.

## What the hash proves

SHA-256 fingerprints canonical configuration JSON. Stable object-key ordering and normalized monetary strings avoid accidental differences such as 0.10 versus 0.1. A hash identifies content; it is not an authentication signature, model-quality score or proof that a model executed. Name/description are preserved separately and included in the displayed diff.

## Contract playground

Choose History → Validate example data. Enter input JSON and optionally a manually supplied expected-output example. The API validates against the snapshot's frozen schemas, returns field paths and safe constraint messages, and does not persist the examples. No provider credentials, worker task, model output or execution result is fabricated.

The supported JSON Schema 2020-12 subset rejects references, custom patterns and unknown keywords; depth, payload size, item count, property count and enums are bounded. The validator checks the schema itself before validating example values, as recommended by the library's API. Literal property names and enum/const data are not confused with schema keywords. [jsonschema validation API](https://python-jsonschema.readthedocs.io/en/stable/validate/).

Example: `{"ticket":7}` fails a required string contract at `/input/ticket`. An output with an unsupported priority fails at `/output/priority`. A valid example establishes shape compatibility only; model behavior and task quality need actual bounded provider execution and evaluations later.

## Keeping frontend and backend aligned

The backend exports OpenAPI without contacting infrastructure. Agent/version/playground TypeScript types are generated from it. CI checks both the exported schema against FastAPI and the generated types against that schema. This removes handwritten duplication for these APIs; workflow and session types remain to be converted when those contracts mature.

## Current boundary and next step

All snapshots in this slice have purpose=test, use configuration schema version 1 and are non-executable. Publishing correctly returns a provider-required error until connection/capability validation exists. The next slice adds a real provider boundary and encrypted credential lifecycle, followed by durable run submission, budget accounting and workers. Existing snapshots will stay readable; any configuration schema migration must produce a new draft/snapshot, never rewrite history.
