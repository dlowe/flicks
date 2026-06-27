"""Attach IMDb links and ratings to events at build time — no API key, no runtime cost.

Two keyless IMDb sources:
- the suggestion endpoint (the site's own search-box backend) maps a title (+year
  when the listing carries one) to a `tt…` id, filling links the theater feeds
  don't provide;
- the official ratings dataset (`title.ratings.tsv.gz`, refreshed daily) supplies
  the average rating for an id.

The suggestion result also carries the film's poster image, so we best-effort
backfill a poster for any film that has an id but no theater-supplied poster.

Ids resolve once and are cached in `imdb_ids.json` (negative results included, so
we don't re-query titles that have no match); posters cache the same way in
`imdb_posters.json`; the ratings file is cached and re-downloaded at most daily.
Feed-provided ids (e.g. ForMovieTickets) are trusted and reused rather than
re-resolved.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import filter as filters
from .models import Event
from .titles import normalize

_DIR = Path(__file__).parent.parent
IDS_CACHE = _DIR / "imdb_ids.json"
POSTERS_CACHE = _DIR / "imdb_posters.json"
RATINGS_FILE = _DIR / "imdb_ratings.tsv.gz"
RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
RATINGS_MAX_AGE = 24 * 3600  # re-download the dataset at most daily

SUGGEST = "https://v2.sg.media-imdb.com/suggestion/{first}/{query}.json"
USER_AGENT = "Mozilla/5.0 (flicks indie-cinema calendar)"
_YEAR = re.compile(r"\((\d{4})\)")
_TT = re.compile(r"(tt\d+)")
# Suggestion result types that are films (exclude TV series, games, people, ...).
_FILM_TYPES = ("feature", "movie", "video", "short", "documentary")


def enrich(events: list[Event]) -> list[Event]:
    """Return events with `imdb` and `rating` filled in where resolvable."""
    by_key: dict[str, list[Event]] = {}
    for e in events:
        by_key.setdefault(filters.key(e.title), []).append(e)

    tconsts = _resolve_ids(by_key)
    ratings = _ratings_for(set(tconsts.values()) - {None})
    posters = _resolve_posters(by_key, tconsts)

    out: list[Event] = []
    for e in events:
        k = filters.key(e.title)
        tt = tconsts.get(k)
        link = e.imdb or (f"https://www.imdb.com/title/{tt}/" if tt else None)
        rating = ratings.get(tt) if tt else None
        poster = e.poster or posters.get(k)  # best-effort: fill a missing poster from IMDb
        out.append(Event(e.title, e.start, e.theater, e.url, poster, link, rating))
    return out


def _resolve_ids(by_key: dict[str, list[Event]]) -> dict[str, str | None]:
    cache = _load_json(IDS_CACHE)

    todo = []
    for k, evs in by_key.items():
        if k in cache:
            continue
        feed_tt = next((_TT.search(e.imdb).group(1) for e in evs if e.imdb and _TT.search(e.imdb)), None)
        if feed_tt:  # the theater already told us the id — trust it
            cache[k] = feed_tt
        else:
            todo.append((k, evs[0].title))

    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (k, _), tt in zip(todo, pool.map(lambda kt: _suggest(kt[1]), todo)):
                cache[k] = tt  # may be None (negative-cached)
        _save_json(IDS_CACHE, cache)

    return {k: cache.get(k) for k in by_key}


def _suggest_films(title: str) -> list[dict]:
    """Exact-title film matches from IMDb's suggestion endpoint, best match first.

    Conservative: only `tt` results whose title matches our loose key and whose
    type is a film. A year in the listing (when present) is preferred; otherwise
    IMDb's own popularity order. Shared by id and poster resolution.
    """
    target = filters.key(title)
    year_m = _YEAR.search(title)
    year = int(year_m.group(1)) if year_m else None
    query = normalize(title).strip().lower()
    query = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", query)).strip()
    if not query:
        return []
    first = next((c for c in query if c.isalnum()), "a")
    url = SUGGEST.format(first=first, query=urllib.parse.quote(query))
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        results = resp.json().get("d", []) if resp.status_code == 200 else []
    except Exception:
        return []

    films = [
        r for r in results
        if str(r.get("id", "")).startswith("tt")
        and filters.key(r.get("l", "")) == target
        and any(t in str(r.get("q", "")).lower() for t in _FILM_TYPES)
    ]
    if year:  # stable sort floats year-matches first, keeping popularity order within
        films.sort(key=lambda r: not (r.get("y") and abs(int(r["y"]) - year) <= 1))
    return films


def _suggest(title: str) -> str | None:
    """Resolve a title to a tt-id (None if no confident match)."""
    films = _suggest_films(title)
    return films[0]["id"] if films else None


def _poster(title: str) -> str | None:
    """Best-effort poster URL for a title, from the suggestion endpoint's image."""
    films = _suggest_films(title)
    return _poster_url(films[0]) if films else None


def _poster_url(r: dict) -> str | None:
    img = r.get("i")
    url = img.get("imageUrl") if isinstance(img, dict) else (img[0] if isinstance(img, (list, tuple)) and img else None)
    if not url:
        return None
    # IMDb/Amazon media URLs accept an inline resize token; the page renders
    # posters ~70px wide, so request a small one (UX = scale to width, QL = quality).
    return re.sub(r"\._V1_.*?(\.\w+)$", r"._V1_QL75_UX190_\1", url)


def _resolve_posters(by_key: dict[str, list[Event]], tconsts: dict[str, str | None]) -> dict[str, str | None]:
    """Posters for films that have an id but no feed-supplied poster, cached (incl. negatives)."""
    cache = _load_json(POSTERS_CACHE)
    todo = [
        (k, evs[0].title) for k, evs in by_key.items()
        if tconsts.get(k) and k not in cache and any(not e.poster for e in evs)
    ]
    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (k, _), poster in zip(todo, pool.map(lambda kt: _poster(kt[1]), todo)):
                cache[k] = poster  # may be None (negative-cached)
        _save_json(POSTERS_CACHE, cache)
    return {k: cache.get(k) for k in by_key}


def _ratings_for(tconsts: set[str]) -> dict[str, float]:
    if not tconsts:
        return {}
    if not _fresh(RATINGS_FILE, RATINGS_MAX_AGE):
        try:
            resp = requests.get(RATINGS_URL, headers={"User-Agent": USER_AGENT}, timeout=120)
            resp.raise_for_status()
            RATINGS_FILE.write_bytes(resp.content)
        except Exception as e:
            if not RATINGS_FILE.exists():
                print(f"  imdb ratings unavailable: {e}")
                return {}

    out: dict[str, float] = {}
    try:
        with gzip.open(RATINGS_FILE, "rt", encoding="utf-8") as f:
            next(f, None)  # header
            for line in f:
                tt, _, rest = line.partition("\t")
                if tt in tconsts:
                    try:
                        out[tt] = float(rest.split("\t", 1)[0])
                    except ValueError:
                        pass
                    if len(out) == len(tconsts):
                        break
    except OSError:
        pass
    return out


def _fresh(path: Path, max_age: float) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < max_age
    except OSError:
        return False


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
