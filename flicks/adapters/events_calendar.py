"""Adapter for The Events Calendar (WordPress / Modern Tribe).

Powers Clinton Street and PAM/Whitsell. Parameterized by base URL + theater
name, since the JSON shape is identical across installs. (Hollywood also runs
WordPress but keeps screenings outside this plugin — see hollywood.py.)
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from ..models import Event

USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"


def fetch(
    base_url: str,
    theater: str,
    *,
    days: int = 30,
    category: str | None = None,
    drop_venue_substr: str | None = None,
) -> list[Event]:
    """Pull events from a The Events Calendar install.

    category: restrict to one Tribe category slug (e.g. "screenings-experiences").
    drop_venue_substr: skip events whose venue name contains this (used to keep a
        shared calendar's other venue out — e.g. PAM's Tomorrow Theater shows).
    """
    base_url = base_url.rstrip("/")
    start = datetime.now().date()
    end = start + timedelta(days=days)

    endpoint = f"{base_url}/wp-json/tribe/events/v1/events"
    params = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "per_page": 50,
    }
    if category:
        params["categories"] = category

    events: list[Event] = []
    page = 1
    while True:
        params["page"] = page
        resp = requests.get(
            endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        for raw in data.get("events", []):
            if drop_venue_substr and drop_venue_substr in _venue_name(raw):
                continue
            events.append(_parse(raw, theater))

        if page >= data.get("total_pages", 1):
            break
        page += 1

    return events


def _venue_name(raw: dict) -> str:
    venue = raw.get("venue")
    return (venue.get("venue") if isinstance(venue, dict) else "") or ""


def _parse(raw: dict, theater: str) -> Event:
    tz = ZoneInfo(raw.get("timezone") or "America/Los_Angeles")
    start = datetime.strptime(raw["start_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)

    image = raw.get("image") or {}
    poster = image.get("url") if isinstance(image, dict) else (image or None)

    return Event(
        title=html.unescape(raw["title"]).strip(),
        start=start,
        theater=theater,
        url=raw.get("url", ""),
        poster=poster,
    )
