"""Adapter for Cinema 21 — Veezi-backed "Flicks" site with a same-origin JSON API.

The site's own frontend fetches /api/movie/playing-now (no auth). Each film
carries a list of sessionTimes with a date + a 12-hour local time string.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from ..models import Event

BASE = "https://www.cinema21.com"
THEATER = "Cinema 21"
TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"


def fetch() -> list[Event]:
    resp = requests.get(
        f"{BASE}/api/movie/playing-now",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()

    events: list[Event] = []
    for film in resp.json():
        title = (film.get("title") or "").strip()
        url = f"{BASE}/movie/{film['url']}" if film.get("url") else BASE
        poster = film.get("imageVerticalUrl") or film.get("imageHorizontalUrl")

        for session in film.get("sessionTimes") or []:
            start = _parse_start(session.get("date"), session.get("time"))
            if start is None:
                continue
            events.append(
                Event(title=title, start=start, theater=THEATER, url=url, poster=poster)
            )

    return events


def _parse_start(date: str | None, time: str | None) -> datetime | None:
    if not date or not time:
        return None
    clean = time.replace(" ", "").upper()  # "9:30pm" -> "9:30PM"
    try:
        t = datetime.strptime(clean, "%I:%M%p").time()
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return datetime.combine(d, t, tzinfo=TZ)
