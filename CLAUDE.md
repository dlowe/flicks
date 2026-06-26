# flicks

Builds a combined webpage of upcoming screenings from Portland indie/rep movie
theaters, with wide releases and non-film events filtered out. Runs locally and
uses **no LLM/tokens at runtime** — it's plain HTTP + parsing. (LLMs were used at
build time to discover each theater's data source and write its adapter.)

## Pipeline

`adapters → list[Event] → 30-day horizon → events.json (full cache) → filter → render → index.html`

- `flicks/main.py` — the registry (`SOURCES`) and orchestration. Each source is a
  callable returning `list[Event]`; one flaky theater can't sink the page.
- `flicks/models.py` — `Event` (title, tz-aware start, theater, url, poster).
- `flicks/render.py` — groups by date, folds same-film/same-theater showings into
  one row, title-cases SHOUTING titles, writes `index.html` from the Jinja template.
- `flicks/filter.py` + `filter.toml` — wide-release / non-film filtering (below).
- `flicks/multiplex.py` — Cinemark now-playing + coming-soon → wide-release denylist.
- `events.json` is the **full** in-window cache (unfiltered); the page is filtered.
  Re-tuning the filter never needs a re-fetch.

## Adapters — theater → platform

Each platform adapter is parameterized and covers multiple theaters:

| Adapter | Theaters | Source |
|---|---|---|
| `events_calendar` | Clinton Street; PAM/Whitsell | WordPress "The Events Calendar" `/wp-json/tribe/events/v1/events` (PAM: `category=screenings-experiences`, drops the Tomorrow venue) |
| `hollywood` | Hollywood | WordPress custom `event` post type (datetime in the title); poster from linked `show`. **Behind Cloudflare → uses `curl_cffi` impersonation.** Parallelized + windowed (~30s). |
| `cinema21` | Cinema 21 | Veezi-backed "Flicks" site `/api/movie/playing-now` |
| `omsi` | OMSI Empirical | Ticketure via `wp-json/omsi/v1/ticketure-events` (filter `venue_short == "Empirical Theater"`) |
| `filmbot` | Tomorrow | Filmbot `wp-json/nj/v1` (uses `_imdb_id`/`_tmdb_id` as a film-vs-live-event flag) |
| `formovietickets` | Studio One, Moreland, Laurelhurst, Academy | static `app.formovietickets.com/schedules/scheduleV1/L{rtn}.json` |
| `indy` | Living Room (317), Cinemagic (40) | INDY/Proludio GraphQL `api-us.indy.systems` with `site-id` header |

Not yet added: **5th Avenue** (Squarespace Events; showtimes buried in `body` HTML;
the theater runs on a summer hiatus so payoff is low).

## Filtering

Decision order per film: **allow > deny > non-film keyword > multiplex > cross-theater > density**.

- `filter.key()` is the loose matching key: lowercased, trailing `(...)` and
  accessibility qualifiers ("Open Captions") stripped, punctuation→space, leading
  article dropped. Merges `ODYSSEY`/`The Odyssey`/`Disclosure Day (Open Caption)`.
- Heuristics: a title at ≥3 distinct *tracked* theaters, or ≥6 showings/day at one,
  is a wide release. Tunable in `filter.toml`.
- **multiplex-subtract** (`multiplex.py`): the principled fix for wide releases that
  play only ONE of our tracked theaters (so no cross-theater signal) or are advance
  previews of not-yet-released films. Subtracts Cinemark's now-playing + coming-soon.
  Spares revivals by construction — old films aren't in the multiplex slate. This is
  why old wide releases shown as revivals (Iron Giant, Scooby-Doo) are kept; see the
  recency principle in this project's memory.
- `allow`/`deny`/`nonfilm_keywords` in `filter.toml` are the manual overrides.
- The page also has a per-film **hide button** (localStorage) for "not my thing".

## Conventions

- Hand-rolled, minimal deps: `requests`, `curl_cffi` (Hollywood only), `jinja2`.
  Stdlib `tomllib` + `zoneinfo` → needs Python 3.11+.
- All times localized to `America/Los_Angeles`.
- Run with `./run.sh` (~30s). See README.md.
