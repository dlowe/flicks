"""Build the Portland indie-cinema page from all theater adapters."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import filter as filters
from . import multiplex
from .adapters import (
    cinema21,
    events_calendar,
    filmbot,
    formovietickets,
    hollywood,
    indy,
    omsi,
    veezi,
)
from .render import render

OUT_DIR = Path(__file__).parent.parent
TZ = ZoneInfo("America/Los_Angeles")
HORIZON_DAYS = 30

# Each source is a no-arg callable returning list[Event].
SOURCES = [
    lambda: events_calendar.fetch("https://cstpdx.com", "Clinton Street Theater"),
    hollywood.fetch,
    cinema21.fetch,
    omsi.fetch,
    lambda: events_calendar.fetch(
        "https://portlandartmuseum.org",
        "PAM CUT / Whitsell",
        category="screenings-experiences",
        drop_venue_substr="Tomorrow",
    ),
    lambda: filmbot.fetch("https://tomorrowtheater.org", "Tomorrow Theater"),
    lambda: formovietickets.fetch(895645, "Studio One", "studioone"),
    lambda: formovietickets.fetch(697452, "Moreland Theater", "moreland"),
    lambda: formovietickets.fetch(3677, "Laurelhurst Theater", "laurelhurst"),
    lambda: formovietickets.fetch(862660, "Academy Theater", "academytheater"),
    lambda: indy.fetch("317", "Living Room Theaters", "https://pdx.livingroomtheaters.com"),
    lambda: indy.fetch("40", "Cinemagic", "https://tickets.thecinemagictheater.com"),
    lambda: veezi.fetch("https://stjohnscinema.com/", "St. Johns Cinema"),
]


def main() -> None:
    events = []
    for source in SOURCES:
        try:
            got = source()
            print(f"  {len(got):3} from {got[0].theater if got else source}")
            events.extend(got)
        except Exception as e:  # one flaky theater shouldn't sink the page
            print(f"  ERR {source}: {e}")

    events = _within_horizon(events)
    events.sort(key=lambda e: (e.start, e.theater))
    print(f"{len(events)} showings total")

    # events.json is the full canonical cache; filtering is applied only to the page.
    events_json = [{**asdict(e), "start": e.start.isoformat()} for e in events]
    (OUT_DIR / "events.json").write_text(json.dumps(events_json, indent=2), encoding="utf-8")

    try:
        wide_keys = frozenset(multiplex.wide_release_keys())
        print(f"multiplex denylist: {len(wide_keys)} wide-release titles")
    except Exception as e:  # a Cinemark hiccup shouldn't sink the page
        print(f"multiplex denylist unavailable: {e}")
        wide_keys = frozenset()

    kept, dropped = filters.apply(events, wide_keys)
    _report_drops(dropped)

    render(kept, OUT_DIR / "index.html")
    print(f"{len(kept)} showings after filter; wrote {OUT_DIR / 'index.html'}")


def _report_drops(dropped):
    if not dropped:
        return
    by_title: dict[str, tuple[str, str, int]] = {}
    for event, reason in dropped:
        k = filters.key(event.title)
        title, _, count = by_title.get(k, (event.title, reason, 0))
        by_title[k] = (title, reason, count + 1)

    print(f"filtered {len(dropped)} showings / {len(by_title)} titles:")
    for title, reason, count in sorted(by_title.values(), key=lambda r: -r[2]):
        print(f"  [{reason}] {title} ({count})")


def _within_horizon(events):
    now = datetime.now(TZ)
    cutoff = now.date() + timedelta(days=HORIZON_DAYS)
    return [e for e in events if e.start >= now and e.start.date() <= cutoff]


if __name__ == "__main__":
    main()
