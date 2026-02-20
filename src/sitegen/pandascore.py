from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests


logger = logging.getLogger(__name__)


class PandaScoreClient:
    def __init__(self, token: str, base_url: str = "https://api.pandascore.co") -> None:
        token = token.strip()
        if not token:
            raise ValueError("token must not be empty")

        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
        )

    def fetch_matches(self, start_dt_utc: datetime, end_dt_utc: datetime) -> list[dict[str, Any]]:
        start_utc = self._to_utc(start_dt_utc)
        end_utc = self._to_utc(end_dt_utc)
        if end_utc <= start_utc:
            raise ValueError("end_dt_utc must be greater than start_dt_utc")

        all_items: list[dict[str, Any]] = []
        total_pages = 0

        day_cursor = start_utc.date()
        last_day = (end_utc - timedelta(microseconds=1)).date()

        while day_cursor <= last_day:
            day_str = day_cursor.isoformat()
            page = 1
            day_pages = 0
            day_received = 0

            while True:
                params = {
                    "filter[begin_at]": day_str,
                    "page[size]": 100,
                    "page[number]": page,
                    "sort": "begin_at",
                }
                response = self._request_with_retries("GET", f"{self.base_url}/matches", params=params)

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise RuntimeError(f"Invalid JSON from PandaScore for day={day_str}, page={page}") from exc

                if not isinstance(payload, list):
                    raise RuntimeError(
                        f"Unexpected PandaScore response shape for day={day_str}, page={page}: "
                        f"{type(payload).__name__}"
                    )

                day_pages += 1
                total_pages += 1

                if not payload:
                    break

                filtered_items = [
                    item
                    for item in payload
                    if self._is_match_in_range(item, start_utc=start_utc, end_utc=end_utc)
                ]
                all_items.extend(filtered_items)
                day_received += len(payload)

                if not self._has_next_page(response.headers.get("Link")):
                    break
                page += 1

            logger.info(
                "PandaScore day=%s pages=%d raw_matches=%d",
                day_str,
                day_pages,
                day_received,
            )
            day_cursor += timedelta(days=1)

        logger.info(
            "PandaScore range %s..%s pages=%d matches=%d",
            start_utc.isoformat(),
            end_utc.isoformat(),
            total_pages,
            len(all_items),
        )
        return all_items

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_begin_at(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_match_in_range(self, item: dict[str, Any], start_utc: datetime, end_utc: datetime) -> bool:
        begin_dt = self._parse_begin_at(item.get("begin_at"))
        if begin_dt is None:
            return False
        return start_utc <= begin_dt < end_utc

    @staticmethod
    def _has_next_page(link_header: str | None) -> bool:
        if not link_header:
            return False
        parts = [p.strip() for p in link_header.split(",") if p.strip()]
        for part in parts:
            if 'rel="next"' in part:
                return True
        return False

    def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        backoffs = [1, 2, 4]
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self.session.request(method, url, timeout=20, **kwargs)
            except requests.RequestException:
                if attempt >= 3:
                    raise
                time.sleep(backoffs[attempt - 1])
                continue

            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt >= 3:
                    response.raise_for_status()
                retry_after = self._get_retry_after_seconds(response.headers.get("Retry-After"))
                if retry_after is not None:
                    time.sleep(retry_after)
                else:
                    time.sleep(backoffs[attempt - 1])
                continue

            response.raise_for_status()
            return response

    @staticmethod
    def _get_retry_after_seconds(value: str | None) -> float | None:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        if value.isdigit():
            return float(value)
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delay = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delay)
