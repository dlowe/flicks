"""Adapter for the INDY (Proludio) platform — Living Room Theaters, Cinemagic, Kiggins.

An unauthenticated GraphQL POST (with the site's numeric site-id header) returns
the site's full movie catalog. We page through it and emit one event per upcoming
published showing. Times come back in UTC, so we localize to Pacific for display.
Site-ids are found via `{site(id:N){name}}` (Living Room 317, Cinemagic 40,
Kiggins 28); there's no public hostname resolver.

Two gotchas the query has to account for:
- `movies` is paginated and defaults to only 10 results — without an explicit
  `limit`/`offset` we'd miss most of the now-playing slate (e.g. Kiggins' "So I
  Married an Axe Murderer"). Limits above ~1000 silently fall back to 10, so we
  page in fixed chunks instead of asking for one huge page.
- Each showing carries a `published` flag, and the catalog spans years; we keep
  only published, still-upcoming showings (drafts like Cinemagic's phantom "Up"
  are unpublished and must not leak through).
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

QUERY = "{movies(limit:%d,offset:%d){data{name urlSlug posterImage showings{time published}}}}"
PAGE = 300  # chunk size; comfortably under the limit at which the API falls back to 10
MAX_OFFSET = 6000  # safety stop, far beyond any real catalog
IMGIX = "https://indy-systems.imgix.net/{}?fit=crop&w=400&h=600&fm=jpeg&auto=format,compress"


def fetch(site_id: str, theater: str, site_url: str) -> list[Event]:
    site_url = site_url.rstrip("/")
    now = datetime.now(TZ)
    events: list[Event] = []
    for movie in _all_movies(site_id):
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
            if start < now:  # catalog includes years of past showings
                continue
            events.append(
                Event(title=title, start=start, theater=theater, url=url, poster=poster)
            )
    return events


def _all_movies(site_id: str) -> list[dict]:
    headers = {"User-Agent": USER_AGENT, "site-id": site_id, "client-type": "consumer"}
    movies: list[dict] = []
    offset = 0
    while offset <= MAX_OFFSET:
        resp = requests.post(
            ENDPOINT, json={"query": QUERY % (PAGE, offset)}, headers=headers, timeout=30
        )
        resp.raise_for_status()
        page = resp.json()["data"]["movies"]["data"]
        movies.extend(page)
        if len(page) < PAGE:  # last page
            break
        offset += PAGE
    return movies
