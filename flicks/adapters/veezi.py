"""Adapter for theaters on the raw Veezi Data API — St. Johns Cinema.

Veezi's API needs the cinema's VeeziAccessToken; St. Johns embeds it in its
homepage HTML, so we scrape it fresh each run (it survives token rotation). The
homepage is behind Cloudflare (curl_cffi impersonation), but the API itself is
not. Sessions carry title + start; posters need a per-film lookup.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from curl_cffi import requests as cffi

from ..models import Event

WEBSESSION = "https://api.us.veezi.com/v1/websession"
FILM = "https://api.us.veezi.com/v1/film/{}"
TZ = ZoneInfo("America/Los_Angeles")
_TOKEN = re.compile(r"AccessToken['\"]?\s*[:=]\s*['\"]([A-Za-z0-9]+)")


def fetch(homepage_url: str, theater: str) -> list[Event]:
    token = _scrape_token(homepage_url)
    headers = {"VeeziAccessToken": token, "Accept": "application/json"}

    sessions = requests.get(WEBSESSION, headers=headers, timeout=30).json()
    films: dict[str, dict] = {}

    events: list[Event] = []
    for s in sessions:
        film = _film(s["FilmId"], films, headers)
        start = datetime.fromisoformat(s["FeatureStartTime"]).replace(tzinfo=TZ)
        events.append(
            Event(
                title=html.unescape(s.get("Title") or "").strip(),
                start=start,
                theater=theater,
                url=s.get("Url") or homepage_url,
                poster=film.get("FilmPosterUrl") or film.get("FilmPosterThumbnailUrl"),
            )
        )
    return events


def _scrape_token(homepage_url: str) -> str:
    home = cffi.get(homepage_url, impersonate="chrome", timeout=30).text
    m = _TOKEN.search(home)
    if not m:
        raise RuntimeError(f"no Veezi access token found at {homepage_url}")
    return m.group(1)


def _film(film_id: str, cache: dict, headers: dict) -> dict:
    if film_id not in cache:
        resp = requests.get(FILM.format(film_id), headers=headers, timeout=30)
        cache[film_id] = resp.json() if resp.status_code == 200 else {}
    return cache[film_id]
