from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class DayRange:
    slug: str
    label_ru: str
    start_dt_utc: datetime
    end_dt_utc: datetime
    date_str_display: str


def _day_bounds_utc_from_local_day(day_local: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = day_local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
    next_start_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), next_start_local.astimezone(timezone.utc)


def get_day_ranges(
    mode: str,
    tz_name: str,
    now_utc: datetime | None = None,
) -> list[DayRange]:
    """
    Return day ranges for yesterday/today/tomorrow.

    mode:
    - "utc": day boundaries are midnight-to-midnight in UTC.
    - "local": day boundaries are midnight-to-midnight in tz_name, converted to UTC.

    tz_name is required for local mode and used for display date in both modes.
    """
    if mode not in {"utc", "local"}:
        raise ValueError("mode must be 'utc' or 'local'")

    tz = ZoneInfo(tz_name)

    base_now_utc = now_utc or datetime.now(timezone.utc)
    if base_now_utc.tzinfo is None:
        base_now_utc = base_now_utc.replace(tzinfo=timezone.utc)
    else:
        base_now_utc = base_now_utc.astimezone(timezone.utc)

    local_now = base_now_utc.astimezone(tz)

    specs = [
        ("yesterday", "Вчера", -1),
        ("today", "Сегодня", 0),
        ("tomorrow", "Завтра", 1),
    ]

    ranges: list[DayRange] = []
    for slug, label_ru, delta in specs:
        if mode == "utc":
            day_utc = (base_now_utc + timedelta(days=delta)).date()
            start_utc = datetime(day_utc.year, day_utc.month, day_utc.day, tzinfo=timezone.utc)
            end_utc = start_utc + timedelta(days=1)
            display_local_date = start_utc.astimezone(tz).date().isoformat()
        else:
            day_local = (local_now + timedelta(days=delta)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_utc, end_utc = _day_bounds_utc_from_local_day(day_local, tz)
            display_local_date = day_local.date().isoformat()

        ranges.append(
            DayRange(
                slug=slug,
                label_ru=label_ru,
                start_dt_utc=start_utc,
                end_dt_utc=end_utc,
                date_str_display=display_local_date,
            )
        )

    return ranges
