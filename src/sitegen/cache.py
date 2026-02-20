from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable


CACHE_DIR = Path(".cache/http")


def _build_cache_key(url: str, headers: dict[str, str] | None) -> str:
    normalized_headers = headers or {}
    headers_part = "\n".join(
        f"{k.lower()}:{v}" for k, v in sorted(normalized_headers.items(), key=lambda x: x[0].lower())
    )
    raw = f"{url}\n{headers_part}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_or_fetch(
    url: str,
    headers: dict[str, str] | None,
    ttl_seconds: int,
    fetcher_callable: Callable[[], Any],
) -> tuple[Any, bool]:
    """
    Return (json_data, was_cached) using file cache in .cache/http.

    Cache files:
    - .cache/http/{sha1}.json
    - .cache/http/{sha1}.meta.json
    """
    key = _build_cache_key(url, headers)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    data_path = CACHE_DIR / f"{key}.json"
    meta_path = CACHE_DIR / f"{key}.meta.json"

    now = time.time()

    # Cache read path: any error = cache miss.
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        saved_at = float(meta.get("saved_at", 0))
        if ttl_seconds > 0 and now - saved_at <= ttl_seconds:
            with data_path.open("r", encoding="utf-8") as f:
                cached_data = json.load(f)
            return cached_data, True
    except Exception:
        pass

    fresh_data = fetcher_callable()

    # Cache write path: write failures should not fail request flow.
    try:
        with data_path.open("w", encoding="utf-8") as f:
            json.dump(fresh_data, f, ensure_ascii=False)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "saved_at": now,
                    "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "ttl_seconds": ttl_seconds,
                    "url": url,
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        pass

    return fresh_data, False
