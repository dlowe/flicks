"""Wide-release / non-film filtering, driven by filter.toml.

Decision order per film: allow > deny > non-film keyword > wide-release heuristics.
Matching uses a loose key (lowercased, leading article and trailing "(...)"
stripped) so "ODYSSEY" / "The Odyssey" / "Obsession (Open Caption)" collapse
onto one title for counting and list lookups.
"""

from __future__ import annotations

import re
import tomllib
from collections import defaultdict
from pathlib import Path

from .models import Event

CONFIG = Path(__file__).parent.parent / "filter.toml"

DEFAULTS = {
    "wide_release_theater_count": 3,
    "dense_showings_per_day": 6,
    "subtract_multiplex": True,
    "allow": [],
    "deny": [],
    "nonfilm_keywords": [],
}

_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_ARTICLE = re.compile(r"^(the|a|an)\s+")
# Accessibility/format qualifiers that shouldn't split a film from itself
# ("Disclosure Day with Open Captions" / "... (Open Caption)" -> "disclosure day").
_QUALIFIER = re.compile(
    r"\b(with\s+)?(open\s+caption(s|ed)?|audio\s+descri\w+|asl\s+interpreted|sensory\s+friendly|subtitled)\b"
)


def key(title: str) -> str:
    t = _TRAILING_PAREN.sub("", title.strip().lower())
    t = re.sub(r"[^\w\s]", " ", t)  # punctuation -> space (colons, apostrophes, etc.)
    t = _QUALIFIER.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return _ARTICLE.sub("", t)


def apply(
    events: list[Event], wide_keys: frozenset[str] = frozenset()
) -> tuple[list[Event], list[tuple[Event, str]]]:
    cfg = _load()
    allow = {key(t) for t in cfg["allow"]}
    deny = {key(t) for t in cfg["deny"]}
    keywords = [k.lower() for k in cfg["nonfilm_keywords"]]
    wide_n = cfg["wide_release_theater_count"]
    dense_n = cfg["dense_showings_per_day"]
    if not cfg["subtract_multiplex"]:
        wide_keys = frozenset()

    theaters: dict[str, set[str]] = defaultdict(set)
    per_day: dict[tuple[str, str, object], int] = defaultdict(int)
    for e in events:
        k = key(e.title)
        theaters[k].add(e.theater)
        per_day[(k, e.theater, e.start.date())] += 1
    max_day: dict[str, int] = defaultdict(int)
    for (k, _, _), count in per_day.items():
        max_day[k] = max(max_day[k], count)

    kept: list[Event] = []
    dropped: list[tuple[Event, str]] = []
    for e in events:
        reason = _classify(e, allow, deny, keywords, wide_keys, theaters, max_day, wide_n, dense_n)
        if reason:
            dropped.append((e, reason))
        else:
            kept.append(e)
    return kept, dropped


def _classify(e, allow, deny, keywords, wide_keys, theaters, max_day, wide_n, dense_n) -> str | None:
    k = key(e.title)
    if k in allow:
        return None
    if k in deny:
        return "deny-list"
    low = e.title.lower()
    for kw in keywords:
        if kw in low:
            return f"non-film: {kw}"
    if k in wide_keys:
        return "wide release: multiplex"
    if len(theaters[k]) >= wide_n:
        return f"wide release: {len(theaters[k])} theaters"
    if max_day[k] >= dense_n:
        return f"wide release: {max_day[k]}/day"
    return None


def _load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        with open(CONFIG, "rb") as f:
            data = tomllib.load(f)
        cfg.update(data.get("heuristics", {}))
        cfg.update(data.get("lists", {}))
    return cfg
