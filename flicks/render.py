"""Render a list of Events into a static index.html, grouped by date then theater."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import Event

_TEMPLATES = Path(__file__).parent / "templates"

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


def render(events: list[Event], out: Path) -> None:
    by_date: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        by_date[e.date_key].append(e)

    days = []
    for date_key in sorted(by_date):
        days.append(
            {
                "label": datetime.strptime(date_key, "%Y-%m-%d").strftime("%A, %B %-d"),
                "showings": _fold(by_date[date_key]),
            }
        )

    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("index.html")
    html = template.render(days=days, generated=datetime.now().strftime("%b %-d, %-I:%M%p"))
    out.write_text(html, encoding="utf-8")


def _fold(events: list[Event]) -> list[dict]:
    """Collapse same-film, same-theater showings on a day into one row of times."""
    rows: dict[tuple[str, str], dict] = {}
    for e in sorted(events, key=lambda e: (e.start, e.theater, e.title)):
        key = (e.theater, e.title)
        row = rows.get(key)
        if row is None:
            rows[key] = {
                "title": smart_titlecase(e.title),
                "theater": e.theater,
                "url": e.url,
                "poster": e.poster,
                "times": [e.time_label],
                "earliest": e.start,
            }
        else:
            row["times"].append(e.time_label)
            row["poster"] = row["poster"] or e.poster
    return sorted(rows.values(), key=lambda r: (r["earliest"], r["theater"], r["title"]))
