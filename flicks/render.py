"""Render a list of Events into a static index.html.

The page is data-driven: we emit one folded row per film+theater+day as JSON
and the page groups, orders (by date / film / theater), date-filters, and hides
client-side. That keeps every view available without a re-fetch and lets a stale
page still trim itself to "from today" when opened days later.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import filter as filters
from .models import Event
from .titles import normalize

_TEMPLATES = Path(__file__).parent / "templates"

# Theater display name -> public homepage, for linking theater names on the page.
THEATER_HOMES = {
    "Clinton Street Theater": "https://cstpdx.com",
    "Hollywood Theatre": "https://hollywoodtheatre.org",
    "Cinema 21": "https://www.cinema21.com",
    "OMSI Empirical Theater": "https://omsi.edu",
    "PAM CUT / Whitsell": "https://portlandartmuseum.org",
    "Tomorrow Theater": "https://tomorrowtheater.org",
    "Studio One": "https://studio1theaters.com",
    "Moreland Theater": "https://morelandtheater.com",
    "Laurelhurst Theater": "https://laurelhursttheater.com",
    "Academy Theater": "https://academytheaterpdx.com",
    "Living Room Theaters": "https://pdx.livingroomtheaters.com",
    "Cinemagic": "https://thecinemagictheater.com",
    "St. Johns Cinema": "https://stjohnscinema.com",
}

# Words kept lowercase mid-title, and tokens kept uppercase (roman numerals),
# when prettifying ALL-CAPS titles from sources like ForMovieTickets/Hollywood.
_MINOR = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of",
    "on", "or", "the", "to", "vs", "with", "nor", "per", "via",
}
_ROMAN = {"ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii"}


def smart_titlecase(title: str) -> str:
    """Title-case a SHOUTING title; leave already mixed-case titles untouched."""
    if any(c.islower() for c in title):
        return title
    words = title.split()
    last = len(words) - 1
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        bare = low.strip(".,:;!?'\"()")
        if bare in _ROMAN:
            out.append(word)
        elif bare in _MINOR and 0 < i < last:
            out.append(low)
        else:
            out.append("-".join(p[:1].upper() + p[1:] for p in low.split("-")))
    return " ".join(out)


def render(events: list[Event], out: Path, health: list[str] | None = None) -> None:
    rows = _fold(events)
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    # Escape "<" so the blob can't terminate the <script> it lives in.
    rows_json = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    now = datetime.now()
    template = env.get_template("index.html")
    html = template.render(
        rows_json=rows_json,
        health=health or [],
        theaters=sorted(THEATER_HOMES.items()),  # all covered theaters, for the modal
        generated=now.strftime("%b %-d, %-I:%M%p"),
        build_id=now.strftime("%Y-%m-%dT%H:%M:%S"),  # for the page's auto-reload check
    )
    out.write_text(html, encoding="utf-8")


def _fold(events: list[Event]) -> list[dict]:
    """One row per film+theater+day, collapsing that day's showtimes into a list.

    `key` is the loose match key (shared with filtering) used for grouping films
    and for the per-film hide; `sort` is the earliest start that day, for
    ordering within a date.
    """
    rows: dict[tuple[str, str, str], dict] = {}
    for e in sorted(events, key=lambda e: (e.start, e.theater, e.title)):
        title = normalize(e.title)
        slot = (e.date_key, e.theater, title)
        row = rows.get(slot)
        if row is None:
            rows[slot] = {
                "date": e.date_key,
                "title": smart_titlecase(title),
                "key": filters.key(e.title),
                "theater": e.theater,
                "home": THEATER_HOMES.get(e.theater),
                "url": e.url,
                "poster": e.poster,
                "imdb": e.imdb,
                "times": [e.time_label],
                "starts": [e.start.isoformat()],  # full per-showtime stamps, for .ics export
                "sort": e.start.isoformat(),
            }
        else:
            row["times"].append(e.time_label)
            row["starts"].append(e.start.isoformat())
            row["poster"] = row["poster"] or e.poster
            row["imdb"] = row["imdb"] or e.imdb
    return sorted(rows.values(), key=lambda r: (r["sort"], r["theater"], r["title"]))
