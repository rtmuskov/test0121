from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.sitegen.cache import get_or_fetch
from src.sitegen.dates import DayRange, get_day_ranges
from src.sitegen.images import build_image_name, download_image
from src.sitegen.normalize import normalize_match
from src.sitegen.pandascore import PandaScoreClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildConfig:
    site_url: str
    pandascore_token: str
    day_mode: str
    tz_name: str
    cache_ttl_seconds: int
    dist_dir: Path
    template_dir: Path
    template_name: str
    assets_src_dir: Path
    assets_out_dir: Path
    assets_img_out_dir: Path
    org_name: str
    download_images: bool


def _load_config() -> BuildConfig:
    load_dotenv()

    raw_site_url = (os.getenv("SITE_URL") or "").strip()
    if not raw_site_url:
        raise RuntimeError("Missing SITE_URL in environment")
    site_url = raw_site_url.rstrip("/")
    if not (site_url.startswith("http://") or site_url.startswith("https://")):
        raise RuntimeError("SITE_URL must start with http:// or https://")

    token = (os.getenv("PANDASCORE_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Missing PANDASCORE_TOKEN in environment")

    day_mode = (os.getenv("DAY_MODE") or "utc").strip().lower()
    tz_name = (os.getenv("TZ_NAME") or "UTC").strip()
    cache_ttl = int((os.getenv("CACHE_TTL_SECONDS") or "120").strip())
    org_name = (os.getenv("ORG_NAME") or "Esports Matches").strip()
    download_images = _env_bool("DOWNLOAD_IMAGES", default=False)

    dist_dir = Path("dist")
    template_dir = Path("src/templates")
    assets_src_dir = Path("public/assets")
    assets_out_dir = dist_dir / "assets"
    assets_img_out_dir = assets_out_dir / "img"

    return BuildConfig(
        site_url=site_url,
        pandascore_token=token,
        day_mode=day_mode,
        tz_name=tz_name,
        cache_ttl_seconds=cache_ttl,
        dist_dir=dist_dir,
        template_dir=template_dir,
        template_name="day.html.j2",
        assets_src_dir=assets_src_dir,
        assets_out_dir=assets_out_dir,
        assets_img_out_dir=assets_img_out_dir,
        org_name=org_name,
        download_images=download_images,
    )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_iso_utc(value: str | None) -> datetime:
    if not value:
        return datetime.max.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_status(match: dict[str, Any]) -> str | None:
    if match.get("is_rescheduled"):
        return "https://schema.org/EventRescheduled"

    status = (match.get("status") or "").strip().lower()
    mapping = {
        "canceled": "https://schema.org/EventCancelled",
        "cancelled": "https://schema.org/EventCancelled",
        "postponed": "https://schema.org/EventPostponed",
        "not_started": "https://schema.org/EventScheduled",
        "running": "https://schema.org/EventScheduled",
        "finished": "https://schema.org/EventCompleted",
    }
    return mapping.get(status)


def _build_schema_json(cfg: BuildConfig, slug: str, matches: list[dict[str, Any]]) -> str:
    page_url = f"{cfg.site_url}/{slug}/"
    org_id = f"{cfg.site_url}/#org"

    graph: list[dict[str, Any]] = [
        {
            "@type": "Organization",
            "@id": org_id,
            "name": cfg.org_name,
            "url": f"{cfg.site_url}/",
        }
    ]

    for idx, m in enumerate(matches):
        match_id = m.get("id")
        event: dict[str, Any] = {
            "@type": "SportsEvent",
            "@id": f"{page_url}#match-{match_id if match_id is not None else idx}",
            "name": m.get("title") or "Esports Match",
            "startDate": m.get("begin_at"),
            "organizer": {"@id": org_id},
            "competitor": [
                {"@type": "SportsTeam", "name": t.get("name") or "Unknown"}
                for t in (m.get("teams") or [])
            ],
        }

        end_at = m.get("end_at")
        if end_at:
            event["endDate"] = end_at

        event_status = _event_status(m)
        if event_status:
            event["eventStatus"] = event_status

        stream_url = m.get("stream_url")
        if stream_url:
            event["eventAttendanceMode"] = "https://schema.org/OnlineEventAttendanceMode"
            event["location"] = {"@type": "VirtualLocation", "url": stream_url}

        graph.append(event)

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def _copy_assets(cfg: BuildConfig) -> None:
    if not cfg.assets_src_dir.exists():
        logger.warning("Assets directory not found: %s", cfg.assets_src_dir)
        return
    cfg.assets_out_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cfg.assets_src_dir, cfg.assets_out_dir, dirs_exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _generate_sitemap(cfg: BuildConfig, slugs: list[str]) -> None:
    urls = "\n".join(
        f"  <url><loc>{cfg.site_url}/{slug}/</loc></url>" for slug in slugs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    _write_text(cfg.dist_dir / "sitemap.xml", xml)


def _generate_robots(cfg: BuildConfig) -> None:
    txt = f"User-agent: *\nAllow: /\n\nSitemap: {cfg.site_url}/sitemap.xml\n"
    _write_text(cfg.dist_dir / "robots.txt", txt)


def _web_img_path(filename: str) -> str:
    return f"/assets/img/{filename}"


def _localize_match_images(match: dict[str, Any], cfg: BuildConfig) -> None:
    if not cfg.download_images:
        return

    match_id = str(match.get("id") or "na")

    game_url = (match.get("game_image_url") or "").strip()
    if game_url:
        game_base = build_image_name("game", game_url, f"game-{match_id}")
        saved = download_image(game_url, cfg.assets_img_out_dir / game_base)
        if saved is not None:
            local = _web_img_path(saved.name)
            match["local_game_icon_path"] = local
            match["game_image_url"] = local

    first_team_local = ""
    teams = match.get("teams") or []
    if isinstance(teams, list):
        for i, team in enumerate(teams):
            if not isinstance(team, dict):
                continue
            team_url = (team.get("image_url") or "").strip()
            if not team_url:
                continue
            team_base = build_image_name(f"team-{i + 1}", team_url, f"team-{match_id}-{i + 1}")
            saved = download_image(team_url, cfg.assets_img_out_dir / team_base)
            if saved is None:
                continue
            local = _web_img_path(saved.name)
            team["image_url"] = local
            if not first_team_local:
                first_team_local = local

    if first_team_local:
        match["local_team_logo_path"] = first_team_local


def build_site() -> None:
    cfg = _load_config()
    day_ranges = get_day_ranges(cfg.day_mode, cfg.tz_name)

    if not cfg.template_dir.joinpath(cfg.template_name).exists():
        raise RuntimeError(
            f"Template not found: {cfg.template_dir / cfg.template_name}. "
            "Expected Jinja2 template day.html.j2"
        )

    env = Environment(
        loader=FileSystemLoader(str(cfg.template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(cfg.template_name)

    client = PandaScoreClient(cfg.pandascore_token)

    if cfg.dist_dir.exists():
        shutil.rmtree(cfg.dist_dir)
    cfg.dist_dir.mkdir(parents=True, exist_ok=True)
    _copy_assets(cfg)
    cfg.assets_img_out_dir.mkdir(parents=True, exist_ok=True)

    rendered_slugs: list[str] = []

    for dr in day_ranges:
        cache_url = (
            f"{client.base_url}/matches"
            f"?start={dr.start_dt_utc.isoformat()}&end={dr.end_dt_utc.isoformat()}"
        )

        try:
            raw_matches, was_cached = get_or_fetch(
                url=cache_url,
                headers={"accept": "application/json"},
                ttl_seconds=cfg.cache_ttl_seconds,
                fetcher_callable=lambda dr=dr: client.fetch_matches(dr.start_dt_utc, dr.end_dt_utc),
            )
        except Exception as exc:
            raise RuntimeError(
                f"API fetch failed for {dr.slug} ({dr.start_dt_utc.isoformat()}..{dr.end_dt_utc.isoformat()}): {exc}"
            ) from exc

        if not isinstance(raw_matches, list):
            raise RuntimeError(f"API returned unexpected payload type for {dr.slug}: {type(raw_matches).__name__}")

        normalized = [normalize_match(item if isinstance(item, dict) else {}) for item in raw_matches]
        for match in normalized:
            _localize_match_images(match, cfg)
        normalized.sort(key=lambda x: _parse_iso_utc(x.get("begin_at")))

        schema_json = _build_schema_json(cfg, dr.slug, normalized)
        canonical = f"{cfg.site_url}/{dr.slug}/"

        logger.info(
            "Build %s: matches=%d source=%s",
            dr.slug,
            len(normalized),
            "cache" if was_cached else "api",
        )

        html = template.render(
            slug=dr.slug,
            label_ru=dr.label_ru,
            date_str_display=dr.date_str_display,
            range_start_utc=dr.start_dt_utc.isoformat(),
            range_end_utc=dr.end_dt_utc.isoformat(),
            matches=normalized,
            matches_json=json.dumps(normalized, ensure_ascii=False),
            schema_json=schema_json,
            seo={
                "title": f"{dr.label_ru}: киберспортивные матчи",
                "description": f"Расписание и результаты киберспортивных матчей за {dr.label_ru.lower()}.",
                "canonical_url": canonical,
            },
            site_url=cfg.site_url,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

        out_file = cfg.dist_dir / dr.slug / "index.html"
        _write_text(out_file, html)
        rendered_slugs.append(dr.slug)

    _generate_sitemap(cfg, rendered_slugs)
    _generate_robots(cfg)

    logger.info("Build completed. Pages=%d output=%s", len(rendered_slugs), cfg.dist_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_site()
