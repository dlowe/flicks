"""Adapter for OMSI's Empirical Theater — WordPress + Ticketure custom API.

The /ticketure-events route returns templates (films) and sessions (showtimes)
as separate lists joined on event_template_id. category=Theater does NOT scope
to one venue, so we filter on venue_short ourselves.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta

import requests

from ..models import Event

ENDPOINT = "https://omsi.edu/wp-json/omsi/v1/ticketure-events"
THEATER = "OMSI Empirical Theater"
VENUE = "Empirical Theater"
USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"


def fetch(*, days: int = 35) -> list[Event]:
    today = datetime.now().date()
    params = {
        "start": today.isoformat(),
        "end": (today + timedelta(days=days)).isoformat(),
        "include_wp_events": 1,
        "category": "Theater",
    }
    resp = requests.get(
        ENDPOINT, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()["data"]

    templates = {
        t["id"]: t
        for t in data["event_template"]["_data"]
        if t.get("venue_short") == VENUE
    }

    events: list[Event] = []
    for session in data["event_session"]["_data"]:
        tmpl = templates.get(session.get("event_template_id"))
        if tmpl is None:
            continue
        start = datetime.fromisoformat(session["start_datetime"])
        events.append(
            Event(
                title=html.unescape(tmpl.get("title") or "").strip(),
                start=start,
                theater=THEATER,
                url=tmpl.get("wp_post_url") or tmpl.get("external_url") or "",
                poster=tmpl.get("image_url") or tmpl.get("wp_featured_image"),
            )
        )
    return events
