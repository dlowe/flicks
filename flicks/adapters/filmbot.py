"""Adapter for Filmbot (Nightjar) — Tomorrow Theater.

The /showtime/listings route gives every upcoming showtime in one call; we join
each to its /show record for the poster, theater-native URL, and the imdb/tmdb
id. That id doubles as a film-vs-live-event flag: Tomorrow mixes screenings with
talks and concerts, so we keep only entries that carry one.
"""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from ..models import Event

TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"


def fetch(base_url: str, theater: str) -> list[Event]:
    base_url = base_url.rstrip("/")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    listings = session.get(f"{base_url}/wp-json/nj/v1/showtime/listings", timeout=30)
    listings.raise_for_status()
    data = listings.json()

    movie_ids = {s["movie_id"] for s in data.get("showtimes", [])}
    shows = {mid: _show(session, base_url, mid) for mid in movie_ids}

    events: list[Event] = []
    for s in data.get("showtimes", []):
        show = shows.get(s["movie_id"])
        if show is None or not _is_film(show):
            continue
        start = datetime.strptime(s["datetime"], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        imdb_id = (show.get("_imdb_id") or "").strip()
        events.append(
            Event(
                title=html.unescape((show.get("title") or {}).get("raw") or "").strip(),
                start=start,
                theater=theater,
                url=show.get("link") or "",
                poster=show.get("featured_media_url"),
                imdb=f"https://www.imdb.com/title/{imdb_id}/" if imdb_id.startswith("tt") else None,
            )
        )
    return events


def _show(session: requests.Session, base_url: str, movie_id: int) -> dict | None:
    resp = session.get(f"{base_url}/wp-json/nj/v1/show/{movie_id}", timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()


def _is_film(show: dict) -> bool:
    return bool(show.get("_imdb_id") or show.get("_tmdb_id"))
