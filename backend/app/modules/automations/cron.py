"""Five-field cron schedules evaluated in an IANA timezone.

Minute resolution keeps every schedule at least 60 seconds apart, matching interval limits.
Daylight saving: a time skipped when clocks move forward runs at the first valid instant
after the jump. When clocks move back, a schedule with fixed hours runs a repeated wall-clock
time only once, so a daily job never makes a second paid run that day; an every-hour (``*``)
schedule keeps following elapsed time through the repeated hour.
"""

import re
from datetime import UTC, datetime
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

from croniter import CroniterError, croniter

from app.core.errors import fail

# Numbers, ranges, steps and three-letter names only: no seconds, macros, hashes or random fields.
PART = re.compile(r"^(\*|(\d{1,2}|[a-z]{3})(-(\d{1,2}|[a-z]{3}))?)(/\d{1,2})?$", re.IGNORECASE)


@cache
def _zones():
    return frozenset(available_timezones())


def _repeated(moment):
    """True for the second occurrence of a wall-clock time when clocks move back."""
    first = moment.replace(tzinfo=None).replace(tzinfo=moment.tzinfo, fold=0)
    return first.utcoffset() != moment.utcoffset()


def following(expression, timezone, after):
    """The first occurrence strictly after ``after``, as a UTC datetime."""
    zone = ZoneInfo(timezone)
    fixed_hours = expression.split()[1] != "*"
    try:
        it = croniter(expression, after.astimezone(zone))
        # Enough to step past every minute of a two-hour fall-back.
        for _ in range(180):
            moment = it.get_next(datetime)
            if not (fixed_hours and _repeated(moment)):
                return moment.astimezone(UTC)
    except CroniterError:
        pass
    fail(422, "CRON_NEVER_DUE", "This schedule has no upcoming date. Check the day and month.")


def upcoming(expression, timezone, after, count=5):
    items = []
    for _ in range(count):
        after = following(expression, timezone, after)
        items.append(after)
    return items


def normalize(expression, timezone):
    """Validate a definition and return its canonical expression. Raises 422 when invalid."""
    fields = expression.split()
    if (
        len(fields) != 5
        or not all(PART.match(part) for field in fields for part in field.split(","))
        or not croniter.is_valid(" ".join(fields))
    ):
        fail(
            422,
            "CRON_INVALID",
            "Use five cron fields: minute, hour, day of month, month and day of week.",
        )
    if timezone not in _zones():
        fail(422, "TIMEZONE_INVALID", "Choose an IANA timezone such as Asia/Karachi or UTC.")
    normalized = " ".join(fields).lower()
    following(normalized, timezone, datetime.now(UTC))
    return normalized
