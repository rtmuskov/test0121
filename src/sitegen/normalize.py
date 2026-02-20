from __future__ import annotations

from datetime import datetime
from typing import Any

STATUS_RU = {
    "not_started": "Не начался",
    "running": "Идёт",
    "finished": "Завершён",
    "canceled": "Отменён",
    "cancelled": "Отменён",
    "postponed": "Перенесён",
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _team_name(team: dict[str, Any]) -> str:
    return team.get("name") or "Unknown"


def _format_iso_for_ui(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw.replace("T", " ").replace("Z", "")
    return dt.strftime("%Y-%m-%d %H:%M")


def _status_ru(value: Any) -> str:
    if not isinstance(value, str):
        return "Неизвестно"
    code = value.strip().lower()
    return STATUS_RU.get(code, value)


def normalize_match(raw: dict) -> dict[str, Any]:
    raw = _safe_dict(raw)

    opponents = _safe_list(raw.get("opponents"))
    teams: list[dict[str, Any]] = []
    for entry in opponents:
        entry_dict = _safe_dict(entry)
        opponent = _safe_dict(entry_dict.get("opponent"))
        teams.append(
            {
                "name": opponent.get("name") or "Unknown",
                "acronym": opponent.get("acronym") or "",
                "image_url": opponent.get("image_url") or "",
            }
        )

    title = raw.get("name") or ""
    if not title:
        if len(teams) >= 2:
            title = f"{_team_name(teams[0])} vs {_team_name(teams[1])}"
        else:
            title = f"Match #{raw.get('id', 'n/a')}"

    streams = _safe_list(raw.get("streams_list"))
    stream_url = ""
    for stream in streams:
        stream_dict = _safe_dict(stream)
        candidate = stream_dict.get("raw_url")
        if isinstance(candidate, str) and candidate.strip():
            stream_url = candidate.strip()
            break

    results = _safe_list(raw.get("results"))
    score_str = "VS"
    if len(teams) >= 2 and len(results) >= 2:
        left = _safe_dict(results[0]).get("score")
        right = _safe_dict(results[1]).get("score")
        if isinstance(left, int) and isinstance(right, int):
            score_str = f"{left}–{right}"

    videogame = _safe_dict(raw.get("videogame"))
    league = _safe_dict(raw.get("league"))
    tournament = _safe_dict(raw.get("tournament"))

    return {
        "id": raw.get("id"),
        "title": title,
        "status": raw.get("status") or "unknown",
        "status_ru": _status_ru(raw.get("status")),
        "begin_at": raw.get("begin_at") or None,
        "begin_at_display": _format_iso_for_ui(raw.get("begin_at")),
        "end_at": raw.get("end_at") or None,
        "end_at_display": _format_iso_for_ui(raw.get("end_at")),
        "is_rescheduled": bool(raw.get("rescheduled")),
        "original_scheduled_at": raw.get("original_scheduled_at") or None,
        "game_name": videogame.get("name") or "",
        "game_image_url": videogame.get("image_url") or "",
        "league_name": league.get("name") or "",
        "tournament_name": tournament.get("name") or "",
        "teams": teams,
        "score_str": score_str,
        "stream_url": stream_url,
        "local_team_logo_path": raw.get("local_team_logo_path") or "",
        "local_game_icon_path": raw.get("local_game_icon_path") or "",
    }
