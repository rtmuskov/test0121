from src.sitegen.normalize import normalize_match


def test_normalize_match_full_data():
    raw = {
        "id": 10,
        "name": "Alpha vs Beta",
        "status": "running",
        "begin_at": "2026-02-20T10:00:00Z",
        "end_at": None,
        "rescheduled": True,
        "original_scheduled_at": "2026-02-20T09:30:00Z",
        "videogame": {"name": "Dota 2", "image_url": "https://img/game.png"},
        "league": {"name": "Pro League"},
        "tournament": {"name": "Spring Cup"},
        "opponents": [
            {"opponent": {"name": "Alpha", "acronym": "ALP", "image_url": "https://img/a.png"}},
            {"opponent": {"name": "Beta", "acronym": "BET", "image_url": "https://img/b.png"}},
        ],
        "results": [{"score": 2}, {"score": 1}],
        "streams_list": [{"raw_url": "https://twitch.tv/test"}],
    }

    got = normalize_match(raw)

    assert got["id"] == 10
    assert got["title"] == "Alpha vs Beta"
    assert got["score_str"] == "2–1"
    assert got["stream_url"] == "https://twitch.tv/test"
    assert len(got["teams"]) == 2


def test_title_fallback_to_teams():
    raw = {
        "id": 11,
        "name": None,
        "opponents": [
            {"opponent": {"name": "Team A"}},
            {"opponent": {"name": "Team B"}},
        ],
        "results": [{"score": 0}, {"score": 0}],
    }

    got = normalize_match(raw)

    assert got["title"] == "Team A vs Team B"


def test_title_fallback_to_match_id():
    raw = {"id": 12, "name": None, "opponents": []}

    got = normalize_match(raw)

    assert got["title"] == "Match #12"


def test_score_fallback_to_vs_and_none_safety():
    raw = {
        "id": 13,
        "name": None,
        "opponents": [None, {"opponent": None}],
        "results": [{"score": "x"}],
        "streams_list": [None, {"raw_url": ""}],
        "videogame": None,
        "league": None,
        "tournament": None,
    }

    got = normalize_match(raw)

    assert got["score_str"] == "VS"
    assert got["stream_url"] == ""
    assert got["game_name"] == ""
    assert got["league_name"] == ""
    assert got["tournament_name"] == ""
    assert len(got["teams"]) == 2
