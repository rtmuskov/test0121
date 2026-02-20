import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, render_template

from src.sitegen.cache import get_or_fetch
from src.sitegen.dates import DayRange, get_day_ranges
from src.sitegen.normalize import normalize_match

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

API_BASE = "https://api.pandascore.co"
API_TIMEOUT_SECONDS = 15
APP_CACHE_TTL_SECONDS = int(os.getenv("APP_CACHE_TTL_SECONDS", "90"))
DAY_MODE = os.getenv("DAY_MODE", "utc")
TZ_NAME = os.getenv("TZ_NAME", "UTC")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:5000").rstrip("/")

app = Flask(__name__)
HTTP = requests.Session()


RU_MONTHS_GEN = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_date_ru(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{d.day} {RU_MONTHS_GEN[d.month]} {d.year} года"


def get_token() -> str | None:
    token = os.getenv("PANDASCORE_TOKEN", "").strip()
    return token or None


def fetch_matches(endpoint: str, date_utc: datetime) -> dict[str, Any]:
    token = get_token()
    date_str = date_utc.strftime("%Y-%m-%d")

    url = f"{API_BASE}/{endpoint}"
    params = {
        "filter[begin_at]": date_str,
        "sort": "begin_at",
        "page[size]": 50,
        "page[number]": 1,
    }
    req = requests.Request("GET", url, params=params)
    prepared = req.prepare()

    if not token:
        return {
            "items": [],
            "error": (
                "PANDASCORE_TOKEN не задан. Добавьте токен в переменную среды "
                "или .env и перезапустите сервер."
            ),
            "source_url": prepared.url,
        }

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    def do_fetch() -> list[dict[str, Any]]:
        response = HTTP.get(
            url,
            params=params,
            headers=headers,
            timeout=API_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Invalid JSON in API response") from exc
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected response shape, expected list")
        return payload

    try:
        payload, _ = get_or_fetch(
            url=prepared.url,
            headers=headers,
            ttl_seconds=APP_CACHE_TTL_SECONDS,
            fetcher_callable=do_fetch,
        )
    except requests.RequestException as exc:
        return {
            "items": [],
            "error": f"Network error: {exc}",
            "source_url": prepared.url,
        }
    except Exception as exc:
        return {
            "items": [],
            "error": str(exc),
            "source_url": prepared.url,
        }

    normalized = [normalize_match(item) for item in payload]
    return {
        "items": normalized,
        "error": None,
        "source_url": prepared.url,
    }


def get_day_range_by_slug(slug: str) -> DayRange:
    ranges = get_day_ranges(DAY_MODE, TZ_NAME)
    for item in ranges:
        if item.slug == slug:
            return item
    raise ValueError(f"Unsupported day slug: {slug}")


def build_page_data(slug: str, endpoint: str) -> dict[str, Any]:
    day_range = get_day_range_by_slug(slug)
    result = fetch_matches(endpoint, day_range.start_dt_utc)

    return {
        "slug": day_range.slug,
        "label": day_range.label_ru,
        "date_utc": day_range.start_dt_utc.strftime("%Y-%m-%d"),
        "date_display": day_range.date_str_display,
        "date_human": format_date_ru(day_range.date_str_display),
        "range_start_utc": day_range.start_dt_utc.isoformat(),
        "range_end_utc": day_range.end_dt_utc.isoformat(),
        "day_mode": DAY_MODE,
        "tz_name": TZ_NAME,
        "endpoint": endpoint,
        "matches": result["items"],
        "error": result["error"],
        "source_url": result["source_url"],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "seo": {
            "title": f"Матчи за {format_date_ru(day_range.date_str_display)} | Esports Pulse",
            "description": f"Киберспортивные матчи за {format_date_ru(day_range.date_str_display)}: расписание, статусы и счет.",
            "canonical_url": f"{SITE_URL}/{day_range.slug}/",
            "og_title": f"Матчи за {format_date_ru(day_range.date_str_display)}",
            "og_description": f"Актуальные киберспортивные матчи за {format_date_ru(day_range.date_str_display)}.",
            "og_url": f"{SITE_URL}/{day_range.slug}/",
        },
    }


@app.route("/")
def home():
    return redirect("/today/", code=302)


@app.route("/yesterday/")
def yesterday_page():
    page = build_page_data("yesterday", "matches/past")
    return render_template("day.html", page=page)


@app.route("/today/")
def today_page():
    page = build_page_data("today", "matches")
    return render_template("day.html", page=page)


@app.route("/tomorrow/")
def tomorrow_page():
    page = build_page_data("tomorrow", "matches/upcoming")
    return render_template("day.html", page=page)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
