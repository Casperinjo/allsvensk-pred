

import os
from datetime import date, datetime, timedelta

import requests

API_KEY = os.environ.get("THESPORTSDB_KEY", "3")
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

ALLSVENSKAN_LEAGUE_ID = "4347"
DAYS_AHEAD = 7  


CACHE_TTL = timedelta(hours=1)
_cache: list[tuple[str, str]] | None = None
_cache_time: datetime | None = None


NAME_MAP = {
    "AIK": "AIK",
    "Brommapojkarna": "Brommapojkarna",
    "Degerfors": "Degerfors",
    "Djurgården": "Djurgarden",
    "Elfsborg": "Elfsborg",
    "GAIS": "GAIS",
    "Halmstad": "Halmstad",
    "Hammarby": "Hammarby",
    "Häcken": "Hacken",
    "IFK Göteborg": "Goteborg",
    "Kalmar": "Kalmar",
    "Malmö": "Malmo FF",
    "Mjällby": "Mjallby",
    "Sirius": "Sirius",
    "Västerås": "Vasteras SK",
    "Örgryte": "Orgryte",
}


def _map_team(api_name: str) -> str:
    
    try:
        return NAME_MAP[api_name]
    except KeyError:
        raise KeyError(
            f"Unmapped team name from TheSportsDB: {api_name!r}. "
            f"Add it to NAME_MAP in src/fixtures.py."
        )


def _fetch_day(day: str) -> list[dict]:

    resp = requests.get(
        f"{BASE_URL}/eventsday.php",
        params={"d": day, "l": ALLSVENSKAN_LEAGUE_ID},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("events") or []


def fetch_upcoming_fixtures(days: int = DAYS_AHEAD) -> list[tuple[str, str]]:
    
    global _cache, _cache_time

    # Serve the cached list if it's still fresh.
    if _cache is not None and _cache_time is not None:
        if datetime.now() - _cache_time < CACHE_TTL:
            return _cache

    fixtures: list[tuple[str, str]] = []
    today = date.today()
    for offset in range(days):
        day = (today + timedelta(days=offset)).isoformat()
        for event in _fetch_day(day):

            if event.get("strStatus") != "NS":
                continue
            home = _map_team(event["strHomeTeam"])
            away = _map_team(event["strAwayTeam"])
            fixtures.append((home, away))

    _cache = fixtures
    _cache_time = datetime.now()
    return fixtures


if __name__ == "__main__":
    # Quick manual check: python -m src.fixtures
    for home, away in fetch_upcoming_fixtures():
        print(f"{home} vs {away}")
