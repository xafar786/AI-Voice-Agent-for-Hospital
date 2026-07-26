from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


PAKISTAN_TZ = ZoneInfo("Asia/Karachi")


def pakistan_now() -> datetime:
    return datetime.now(PAKISTAN_TZ)


def pakistan_today() -> date:
    return pakistan_now().date()


def pakistan_day_utc_bounds(moment: datetime | None = None) -> tuple[datetime, datetime]:
    current = moment or pakistan_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=PAKISTAN_TZ)
    else:
        current = current.astimezone(PAKISTAN_TZ)

    start_local = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )
