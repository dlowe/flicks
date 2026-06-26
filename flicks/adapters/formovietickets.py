"""Adapter for ForMovieTickets (RTS) — Studio One, Moreland, Laurelhurst.

Each theater's full schedule is a single unauthenticated static JSON keyed by
its account id (rtn). Showtimes are local wall-clock with no zone; we localize
to Pacific ourselves since the feed's offset fields are unreliable.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from ..models import Event

APP = "https://app.formovietickets.com"
TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"
POSTER_TYPE = 1


def fetch(rtn: int | str, theater: str, slug: str) -> list[Event]:
    resp = requests.get(
        f"{APP}/schedules/scheduleV1/L{rtn}.json",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    loc = resp.json()["location"]

    graphics = {g["id"]: g for g in loc.get("Graphics", [])}
    detail_url = f"{APP}/?id={slug}&rtn={rtn}"

    events: list[Event] = []
    for title in loc.get("Titles", []):
        name = (title.get("title") or "").strip()
        poster = _poster(title.get("Graphics", []), graphics)
        for show in title.get("Shows", []):
            start = datetime.fromisoformat(show["time"]).replace(tzinfo=TZ)
            events.append(
                Event(title=name, start=start, theater=theater, url=detail_url, poster=poster)
            )
    return events


def _poster(ids: list[int], graphics: dict) -> str | None:
    for gid in ids:
        g = graphics.get(gid)
        if g and g.get("type") == POSTER_TYPE and g.get("hash"):
            return f"{APP}/schedules/graphics/{g['hash']}_200_300_85.jpg"
    return None
