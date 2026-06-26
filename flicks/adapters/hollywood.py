"""Adapter for Hollywood Theatre.

Hollywood runs WordPress but does NOT keep screenings in The Events Calendar
(that feed holds only monthly member meetings). Screenings are a custom 'event'
post type with the datetime encoded in the title ("FILM - 2026-08-03 7:30pm")
and no usable meta; the poster lives on the linked 'show' post. We page through
events a calendar-month at a time via the search param, then join to shows for
posters. The site sits behind a Cloudflare TLS-fingerprint challenge, so we
fetch with curl_cffi browser impersonation.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from curl_cffi import requests

from ..models import Event

BASE = "https://hollywoodtheatre.org"
THEATER = "Hollywood Theatre"
TZ = ZoneInfo("America/Los_Angeles")
IMPERSONATE = "chrome"

_TITLE = re.compile(
    r"^(?P<film>.*?)\s*[–—-]\s*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{1,2}:\d{2})(?P<ap>[ap]m)",
    re.I,
)
_SLUG_DATE = re.compile(r"-\d{4}-\d{2}-\d{2}-\d+[ap]m$", re.I)


def fetch(*, days: int = 30) -> list[Event]:
    now = datetime.now(TZ)
    cutoff = (now + timedelta(days=days)).date()

    # Parse screenings, keeping only the in-window ones so we don't fetch shows
    # for past screenings the horizon would drop anyway.
    rows: list[tuple[str, datetime, str, str]] = []
    seen: set[tuple[str, datetime]] = set()
    for month in _months_spanning(now.date(), cutoff):
        for raw in _events_for_month(month):
            parsed = _parse_event(raw)
            if parsed is None:
                continue
            film, start, slug = parsed
            if start < now or start.date() > cutoff or (film, start) in seen:
                continue
            seen.add((film, start))
            rows.append((film, start, slug, raw.get("link") or BASE))

    # Fetch each distinct show once, in parallel — this is the slow part.
    slugs = {slug for _, _, slug, _ in rows if slug}
    with ThreadPoolExecutor(max_workers=8) as pool:
        shows = dict(zip(slugs, pool.map(_fetch_show, slugs)))

    # Link to the per-screening event page: it reliably exists, whereas some
    # show permalinks 404 despite the show post being published.
    return [
        Event(
            title=film,
            start=start,
            theater=THEATER,
            url=link,
            poster=_poster(shows.get(slug)),
        )
        for film, start, slug, link in rows
    ]


def _events_for_month(month: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE}/wp-json/wp/v2/event",
            params={"search": month, "per_page": 100, "page": page},
            impersonate=IMPERSONATE,
            timeout=30,
        )
        resp.raise_for_status()
        out.extend(resp.json())
        if page >= int(resp.headers.get("X-WP-TotalPages", 1)):
            break
        page += 1
    return out


def _parse_event(raw: dict):
    title = html.unescape((raw.get("title") or {}).get("rendered", ""))
    m = _TITLE.match(title)
    if not m:
        return None
    try:
        naive = datetime.strptime(
            f"{m['date']} {m['time']}{m['ap'].upper()}", "%Y-%m-%d %I:%M%p"
        )
    except ValueError:
        return None
    slug = _SLUG_DATE.sub("", raw.get("slug", ""))
    return m["film"].strip(), naive.replace(tzinfo=TZ), slug


def _fetch_show(slug: str) -> dict | None:
    resp = requests.get(
        f"{BASE}/wp-json/wp/v2/show",
        params={"slug": slug},
        impersonate=IMPERSONATE,
        timeout=30,
    )
    if resp.status_code == 200 and resp.json():
        return resp.json()[0]
    return None


def _poster(show: dict | None) -> str | None:
    if not show:
        return None
    images = (show.get("yoast_head_json") or {}).get("og_image") or []
    return images[0].get("url") if images else None


def _months_spanning(start, end) -> list[str]:
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months
