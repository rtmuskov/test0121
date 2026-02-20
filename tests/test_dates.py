from datetime import datetime, timezone

import pytest

from src.sitegen.dates import get_day_ranges


def _by_slug(items):
    return {x.slug: x for x in items}


def test_get_day_ranges_utc_mode_fixed_now():
    now = datetime(2026, 2, 20, 15, 30, tzinfo=timezone.utc)

    got = _by_slug(get_day_ranges("utc", "Europe/Moscow", now_utc=now))

    assert got["today"].start_dt_utc.isoformat() == "2026-02-20T00:00:00+00:00"
    assert got["today"].end_dt_utc.isoformat() == "2026-02-21T00:00:00+00:00"
    assert got["yesterday"].start_dt_utc.isoformat() == "2026-02-19T00:00:00+00:00"
    assert got["tomorrow"].start_dt_utc.isoformat() == "2026-02-21T00:00:00+00:00"


def test_get_day_ranges_local_mode_fixed_now():
    now = datetime(2026, 2, 20, 15, 30, tzinfo=timezone.utc)

    got = _by_slug(get_day_ranges("local", "Europe/Moscow", now_utc=now))

    assert got["today"].start_dt_utc.isoformat() == "2026-02-19T21:00:00+00:00"
    assert got["today"].end_dt_utc.isoformat() == "2026-02-20T21:00:00+00:00"
    assert got["today"].date_str_display == "2026-02-20"


def test_get_day_ranges_invalid_mode():
    with pytest.raises(ValueError):
        get_day_ranges("bad", "UTC", now_utc=datetime(2026, 2, 20, tzinfo=timezone.utc))
