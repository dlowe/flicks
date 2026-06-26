"""Adapter for the INDY (Proludio) platform — Living Room Theaters, Cinemagic.

A single unauthenticated GraphQL POST (with the site's numeric site-id header)
returns the catalog; we keep movies that have showings and emit one event each.
Times come back in UTC, so we localize to Pacific for display. The site-id is
baked into each tenant's JS bundle (Living Room 317, Cinemagic 40).

Showings carry a `published` flag; draft showings (published:false) are not on
the public site and must be dropped — otherwise unannounced placeholders leak
through (e.g. Cinemagic's phantom "Up").
"""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from ..models import Event

ENDPOINT = "https://api-us.indy.systems/graphql"
TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "flicks/0.1 (local indie-cinema calendar)"

QUERY = "{movies{data{name urlSlug posterImage showings{time published}}}}"
IMGIX = "https://indy-systems.imgix.net/{}?fit=crop&w=400&h=600&fm=jpeg&auto=format,compress"


def fetch(site_id: str, theater: str, site_url: str) -> list[Event]:
    resp = requests.post(
        ENDPOINT,
        json={"query": QUERY},
        headers={
            "User-Agent": USER_AGENT,
            "site-id": site_id,
            "client-type": "consumer",
        },
        timeout=30,
    )
    resp.raise_for_status()
    movies = resp.json()["data"]["movies"]["data"]

    site_url = site_url.rstrip("/")
    events: list[Event] = []
    for movie in movies:
        showings = movie.get("showings") or []
        if not showings:
            continue
        title = html.unescape(movie.get("name") or "").strip()
        url = f"{site_url}/movie/{movie['urlSlug']}" if movie.get("urlSlug") else site_url
        poster = IMGIX.format(movie["posterImage"]) if movie.get("posterImage") else None

        for showing in showings:
            if not showing.get("published", True):
                continue
            start = datetime.fromisoformat(showing["time"]).astimezone(TZ)
            events.append(
                Event(title=title, start=start, theater=theater, url=url, poster=poster)
            )
    return events
