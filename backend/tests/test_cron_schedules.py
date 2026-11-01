import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.automations import cron, service
from app.modules.automations.models import WorkflowAutomation
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.runtime import execute
from tests.conftest import headers
from tests.test_automations import automation

NY = "America/New_York"


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def code(call):
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.detail["code"]


def test_rejects_nonstandard_or_impossible_definitions():
    for bad in ("* * * * * *", "@daily", "H * * * *", "R 1 * * *", "61 * * * *", "* * *", "0 9 * * 1;"):
        assert code(lambda bad=bad: cron.normalize(bad, "UTC")) == "CRON_INVALID"
    assert code(lambda: cron.normalize("0 0 30 2 *", "UTC")) == "CRON_NEVER_DUE"
    assert code(lambda: cron.normalize("0 9 * * *", "Mars/Base")) == "TIMEZONE_INVALID"
    assert cron.normalize(" 0  9 * *  MON-FRI ", "Asia/Karachi") == "0 9 * * mon-fri"
    assert cron.following("0 0 29 2 *", "UTC", utc("2026-11-01T00:00")) == utc("2028-02-29T00:00")


def test_weekday_schedule_in_timezone_without_daylight_saving():
    # Friday 10:00 Karachi (UTC+5) -> Monday 09:00 Karachi.
    assert cron.following("0 9 * * mon-fri", "Asia/Karachi", utc("2026-10-30T05:00")) == utc(
        "2026-11-02T04:00"
    )


def test_spring_forward_runs_skipped_time_once_after_the_jump():
    # 2026-03-08 02:30 does not exist in New York; it runs at 03:00 EDT instead.
    assert cron.upcoming("30 2 * * *", NY, utc("2026-03-07T08:00"), 2) == [
        utc("2026-03-08T07:00"),
        utc("2026-03-09T06:30"),
    ]


def test_fall_back_runs_fixed_hour_once_but_wildcard_hour_follows_elapsed_time():
    # 2026-11-01 01:00-01:59 happens twice in New York.
    assert cron.upcoming("30 1 * * *", NY, utc("2026-10-31T12:00"), 2) == [
        utc("2026-11-01T05:30"),
        utc("2026-11-02T06:30"),
    ]
    assert cron.upcoming("* 1 * * *", NY, utc("2026-11-01T05:58"), 2) == [
        utc("2026-11-01T05:59"),
        utc("2026-11-02T06:00"),
    ]
    assert cron.upcoming("*/30 * * * *", NY, utc("2026-11-01T04:40"), 5) == [
        utc("2026-11-01T05:00"),
        utc("2026-11-01T05:30"),
        utc("2026-11-01T06:00"),
        utc("2026-11-01T06:30"),
        utc("2026-11-01T07:00"),
    ]


def test_cron_automation_coalesces_downtime_to_next_wall_clock_time(client, owner, db):
    base, interval = automation(client, owner, "schedule")
    archived = client.delete(f"{base}/automations/{interval['id']}", headers=headers(client))
    assert archived.status_code == 204
    body = {
        "name": "Weekday digest",
        "kind": "schedule",
        "version_id": interval["version_id"],
        "cron_expression": "0 9 * * MON-FRI",
        "timezone": "Asia/Karachi",
        "input": {"ticket": "private cron input"},
    }
    created = client.post(base + "/automations", headers=headers(client), json=body)
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["cron_expression"] == "0 9 * * mon-fri"
    assert schedule["timezone"] == "Asia/Karachi" and schedule["interval_seconds"] is None
    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))
    due = row.next_due_at
    assert due.astimezone(ZoneInfo("Asia/Karachi")).hour == 9
    # Three days of downtime produce one run, then the cursor moves past "now".
    now = due + timedelta(days=3)
    assert service.tick(client.app.state.settings, now) == 1
    db.expire_all()
    assert row.last_due_at == due
    assert row.next_due_at == cron.following("0 9 * * mon-fri", "Asia/Karachi", now)
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.automation_id == row.id))
    execute(str(run.id), client.app.state.settings)
    assert client.get(f"{base}/workflow-runs/{run.id}").json()["output"] == {
        "ticket": "private cron input"
    }
    assert service.tick(client.app.state.settings, now) == 0
    assert "private cron input" not in str(client.get(base + "/automations").json())


def test_cron_contract_preview_and_database_binding(client, owner, db):
    base, hook = automation(client, owner)
    _, schedule = automation(client, owner, "schedule")
    version = schedule["version_id"]
    common = {"name": "Bad", "kind": "schedule", "version_id": version, "input": {"ticket": "x"}}
    for extra in (
        {"cron_expression": "0 9 * * *", "interval_seconds": 60},
        {"interval_seconds": 60, "timezone": "UTC"},
        {},
    ):
        response = client.post(base + "/automations", headers=headers(client), json={**common, **extra})
        assert response.status_code == 422, extra
    hook_body = {**common, "kind": "webhook", "version_id": hook["version_id"], "input": None}
    response = client.post(
        base + "/automations",
        headers=headers(client),
        json={**hook_body, "cron_expression": "0 9 * * *"},
    )
    assert response.status_code == 422
    for expression, error in (("* * * * * *", "CRON_INVALID"), ("0 0 31 4 *", "CRON_NEVER_DUE")):
        response = client.post(
            base + "/automations",
            headers=headers(client),
            json={**common, "cron_expression": expression},
        )
        assert response.status_code == 422 and response.json()["error"]["code"] == error
    defaulted = client.post(
        base + "/automations",
        headers=headers(client),
        json={**common, "name": "UTC default", "cron_expression": "15 * * * *"},
    )
    assert defaulted.status_code == 201 and defaulted.json()["timezone"] == "UTC"

    preview = client.get(
        base + "/automations/schedule-preview",
        params={"cron_expression": "0 9 * * MON", "timezone": "Asia/Karachi"},
    )
    assert preview.status_code == 200, preview.text
    times = [datetime.fromisoformat(value) for value in preview.json()["occurrences"]]
    assert preview.json()["cron_expression"] == "0 9 * * mon" and len(times) == 5
    assert all(t.weekday() == 0 and t.hour == 4 and t.minute == 0 for t in times)
    assert times == sorted(times) and len(set(times)) == 5
    bad = client.get(
        base + "/automations/schedule-preview",
        params={"cron_expression": "0 9 * * *", "timezone": "Nowhere/City"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "TIMEZONE_INVALID"

    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))
    row.cron_expression = "0 9 * * *"
    row.timezone = "UTC"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
