from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


_INVALID_FILE_CHARS = re.compile(r"[^a-zA-Z0-9._-]+")
_EXT_RE = re.compile(r"\.(png|jpg|jpeg|webp|gif|svg|avif)$", re.IGNORECASE)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    clean = _INVALID_FILE_CHARS.sub("-", (name or "").strip()).strip("-.").lower()
    if not clean:
        clean = "img"
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip("-.")
    return clean or "img"


def _pick_extension(url: str, content_type: str | None) -> str:
    path = urlparse(url).path or ""
    match = _EXT_RE.search(path)
    if match:
        ext = match.group(1).lower()
        return ".jpg" if ext == "jpeg" else f".{ext}"

    ctype = (content_type or "").lower()
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"
    if "webp" in ctype:
        return ".webp"
    if "gif" in ctype:
        return ".gif"
    if "svg" in ctype:
        return ".svg"
    if "avif" in ctype:
        return ".avif"
    return ".img"


def download_image(
    url: str | None,
    out_path: Path,
    timeout_seconds: int = 10,
    max_retries: int = 3,
) -> Path | None:
    if not url:
        return None

    src = url.strip()
    if not src:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    backoffs = [1, 2, 4]
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = requests.get(src, timeout=timeout_seconds)
            if response.status_code >= 400:
                raise requests.HTTPError(f"HTTP {response.status_code} for {src}")

            ext = _pick_extension(src, response.headers.get("Content-Type"))
            stem = sanitize_filename(out_path.stem)
            target = out_path.with_name(f"{stem}{ext}")
            target.write_bytes(response.content)
            return target
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])

    if last_error:
        return None
    return None


def build_image_name(prefix: str, source_url: str, fallback_id: str) -> str:
    parsed = urlparse(source_url)
    source_tail = Path(parsed.path).name
    base_hint = sanitize_filename(Path(source_tail).stem or fallback_id)
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
    return sanitize_filename(f"{prefix}-{base_hint}-{digest}")
