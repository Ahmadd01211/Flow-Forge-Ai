# Calendar (cron) schedules

Interval schedules answer "every N seconds". Most business automations instead say "every weekday at 09:00 Karachi time". A cron schedule is the same durable binding described in [real workflow triggers](13-WEBHOOKS-AND-SCHEDULES.md), with a calendar rule and an IANA timezone in place of the interval.

## Try it locally

1. Publish a workflow whose entry node is a **Schedule trigger**.
2. Open **Triggers & schedules**, choose that version and select **Calendar (cron)**.
3. Pick a preset or type an expression, for example `0 9 * * 1-5`. The timezone defaults to your browser's zone; change it to the zone the business actually runs in.
4. Select **Show next runs**. The server computes the next five occurrences and the page lists them in the schedule's timezone.
5. Enter input JSON and create the automation. The card shows `Cron 0 9 * * 1-5 · Asia/Karachi` and the next due time.

## Supported expressions

Exactly five fields: minute, hour, day of month, month, day of week. Each field accepts `*`, numbers, ranges (`1-5`), steps (`*/15`, `0-30/10`), comma lists and three-letter names (`mon-fri`, `jan`). Expressions are stored lowercase with single spaces.

Rejected on purpose: seconds fields, `@daily`-style macros, hashed (`H`) and random (`R`) fields, and dates that never happen such as `0 0 30 2 *` (`CRON_NEVER_DUE`). Minute resolution keeps every cron schedule at least 60 seconds apart, matching the interval minimum. When both day of month and day of week are restricted, either one matches, as in classic cron.

## Daylight saving

UTC intervals ignore clock changes. Calendar rules cannot, so the policy is explicit:

| Situation | Behavior | Example in America/New_York |
|---|---|---|
| Clocks move forward and a scheduled time does not exist | Runs once at the first valid time after the jump | `30 2 * * *` runs at 03:00 EDT on 8 March 2026 |
| Clocks move back, fixed hour | The repeated wall-clock time runs only the first time | `30 1 * * *` runs once on 1 November 2026, not twice |
| Clocks move back, hour field is `*` | Keeps following elapsed time through the repeated hour | `*/30 * * * *` runs every 30 real minutes |

The fixed-hour rule prevents a daily paid workflow from running twice on the change day. Asia/Karachi and UTC have no daylight saving, so none of this applies there. Timezone rules come from the `tzdata` package pinned in `requirements.lock`; updating it changes future occurrences after a government changes its clocks.

## Delivery and downtime

Nothing else changes in the delivery path. Maintenance locks one due binding, checks permissions and dependencies, inserts the run with the slot time as its idempotency key and advances the cursor in the same transaction. For cron, the next cursor is the first occurrence strictly after the later of the slot and the current time. Downtime across several occurrences therefore produces one coalesced run, then resumes on the calendar instead of bursting paid calls. Backpressure, permission loss and invalid targets behave exactly as for intervals.

## API and data

- Migration `0024` adds nullable `cron_expression` (100) and `timezone` (64) columns. A database check guarantees a schedule has either a 60–86400 second interval or a cron expression with a timezone, never both; webhooks have neither. Downgrade refuses while cron rows exist.
- `POST /api/v1/workspaces/{workspace}/automations` accepts `cron_expression` and an optional `timezone` (default `UTC`) for `kind: "schedule"`, instead of `interval_seconds`.
- `GET /api/v1/workspaces/{workspace}/automations/schedule-preview?cron_expression=…&timezone=…` returns the canonical expression and the next five UTC occurrences. Any workspace member can preview; it changes nothing.
- Error codes: `CRON_INVALID`, `CRON_NEVER_DUE`, `TIMEZONE_INVALID`.

## Decisions and alternatives

Use `croniter` (maintained by pallets-eco) for field parsing and matching, and keep the daylight-saving policy in FlowForge's own `automations/cron.py`, where tests pin it. A hand-written cron parser would be more code to own with no benefit. Celery Beat and a dedicated scheduler were rejected for the same reason as before: PostgreSQL already owns the atomic run-plus-cursor transaction.

Reconsider when customers need business calendars (holidays), "last weekday of month", per-run input templating from the slot time, or very large due queues.

## Tests

`tests/test_cron_schedules.py` covers rejected forms, leap days, a non-DST weekday schedule, the spring-forward and fall-back rules, downtime coalescing through `tick`, the API contract and preview, encrypted input staying out of listings, and the database check constraint. Migration `0024` was also downgraded and re-applied on the isolated test database.
