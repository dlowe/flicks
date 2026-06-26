"""Build the Portland indie-cinema page from all theater adapters."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import filter as filters
from . import multiplex
from .models import Event
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
EVENTS_CACHE = OUT_DIR / "events.json"
MULTIPLEX_CACHE = OUT_DIR / "multiplex.json"  # last wide-release denylist, for --render-only

# Each source is (theater label, no-arg callable returning list[Event]). The
# label names the theater even when a fetch fails or returns nothing, which the
# health check needs.
SOURCES = [
    ("Clinton Street Theater",
     lambda: events_calendar.fetch("https://cstpdx.com", "Clinton Street Theater")),
    ("Hollywood Theatre", hollywood.fetch),
    ("Cinema 21", cinema21.fetch),
    ("OMSI Empirical Theater", omsi.fetch),
    ("PAM CUT / Whitsell",
     lambda: events_calendar.fetch(
         "https://portlandartmuseum.org",
         "PAM CUT / Whitsell",
         category="screenings-experiences",
         drop_venue_substr="Tomorrow",
     )),
    ("Tomorrow Theater",
     lambda: filmbot.fetch("https://tomorrowtheater.org", "Tomorrow Theater")),
    ("Studio One", lambda: formovietickets.fetch(895645, "Studio One", "studioone")),
    ("Moreland Theater", lambda: formovietickets.fetch(697452, "Moreland Theater", "moreland")),
    ("Laurelhurst Theater", lambda: formovietickets.fetch(3677, "Laurelhurst Theater", "laurelhurst")),
    ("Academy Theater", lambda: formovietickets.fetch(862660, "Academy Theater", "academytheater")),
    ("Living Room Theaters",
     lambda: indy.fetch("317", "Living Room Theaters", "https://pdx.livingroomtheaters.com")),
    ("Cinemagic",
     lambda: indy.fetch("40", "Cinemagic", "https://tickets.thecinemagictheater.com")),
    ("St. Johns Cinema", lambda: veezi.fetch("https://stjohnscinema.com/", "St. Johns Cinema")),
]


def main() -> None:
    events = []
    raw_counts: dict[str, int | None] = {}  # None == fetch raised
    for label, source in SOURCES:
        try:
            got = source()
            raw_counts[label] = len(got)
            print(f"  {len(got):3} from {label}")
            events.extend(got)
        except Exception as e:  # one flaky theater shouldn't sink the page
            raw_counts[label] = None
            print(f"  ERR {label}: {e}")

    ailing = _health(raw_counts)
    if ailing:
        print(f"health: {len(ailing)} source(s) need attention: {', '.join(ailing)}")

    events = _within_horizon(events)
    events.sort(key=lambda e: (e.start, e.theater))
    print(f"{len(events)} showings total")

    # events.json is the full canonical cache; filtering is applied only to the page.
    events_json = [{**asdict(e), "start": e.start.isoformat()} for e in events]
    EVENTS_CACHE.write_text(json.dumps(events_json, indent=2), encoding="utf-8")

    try:
        wide_keys = frozenset(multiplex.wide_release_keys())
        print(f"multiplex denylist: {len(wide_keys)} wide-release titles")
        MULTIPLEX_CACHE.write_text(json.dumps(sorted(wide_keys), indent=2), encoding="utf-8")
    except Exception as e:  # a Cinemark hiccup shouldn't sink the page
        print(f"multiplex denylist unavailable: {e}")
        wide_keys = frozenset()

    kept, dropped = filters.apply(events, wide_keys)
    _report_drops(dropped)

    render(kept, OUT_DIR / "index.html", health=ailing)
    print(f"{len(kept)} showings after filter; wrote {OUT_DIR / 'index.html'}")


def render_only() -> None:
    """Rebuild index.html from the cached events.json + multiplex.json — no network.

    For iterating on filtering/rendering without re-fetching every theater. Uses
    the last full run's multiplex denylist; health banners are omitted (nothing
    was fetched this pass).
    """
    events = _load_cached_events()
    try:
        wide_keys = frozenset(json.loads(MULTIPLEX_CACHE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        print("no cached multiplex denylist (run ./run.sh once); rendering without it")
        wide_keys = frozenset()

    kept, dropped = filters.apply(events, wide_keys)
    _report_drops(dropped)
    render(kept, OUT_DIR / "index.html", health=[])
    print(f"{len(kept)} showings after filter (render-only); wrote {OUT_DIR / 'index.html'}")


def _load_cached_events() -> list[Event]:
    data = json.loads(EVENTS_CACHE.read_text(encoding="utf-8"))
    out = []
    for e in data:
        e = dict(e)
        e["start"] = datetime.fromisoformat(e["start"])
        out.append(Event(**e))
    return out


# Per-source fetch health. A source is "ailing" if its fetch raised, or if it
# returned nothing this run despite having returned listings on a prior run
# (a likely sign its site changed) — distinguishing that from a theater that is
# simply, legitimately empty right now. State persists in health.json.
HEALTH_STATE = OUT_DIR / "health.json"


def _health(raw_counts: dict[str, int | None]) -> list[str]:
    try:
        state = json.loads(HEALTH_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}

    now = datetime.now(TZ).isoformat()
    ailing: list[str] = []
    for label, count in raw_counts.items():
        prev = state.get(label, {})
        if count is None:
            ailing.append(label)
        elif count == 0:
            if prev.get("last_count"):  # it has produced listings before
                ailing.append(label)
        else:
            state[label] = {"last_ok": now, "last_count": count}

    HEALTH_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return sorted(ailing)


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
    render_only() if "--render-only" in sys.argv else main()
