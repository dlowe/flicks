# flicks

A combined calendar of what's playing at Portland's indie & repertory movie
theaters — built locally, with wide releases and non-film events filtered out.
The output is a single self-contained webpage.

## First-time setup

Needs **Python 3.11+** (uses the stdlib `tomllib`).

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Run it

```bash
./run.sh          # fetch every theater, rebuild events.json + index.html (~30s)
open index.html   # view the page
```

Re-run `./run.sh` whenever you want fresh listings. It needs no API keys and
makes no LLM calls — just plain web requests.

To iterate on filtering or the page without re-fetching, `./render.sh` rebuilds
`index.html` from the cached `events.json` (and the last run's multiplex denylist)
in a fraction of a second.

## The page

- **Search** filters by film title or theater as you type (kept across refreshes).
- The current day/theater header stays pinned while you scroll.
- **By date / by film / by theater** toggle at the top (your choice is remembered).
  "By theater" lists each film once per theater with all its dates.
- Screenings in the **next ~3 days** are emphasized (Today/Tomorrow labelled), and
  films rated **IMDb 9.0+** get a highlighted rating pill.
- Showings you haven't seen yet get a green **New** marker, so aggressive filtering
  doesn't hide things that have only just appeared. A showing counts as seen once
  it's been on screen for about a second; it's tracked per-showing in your browser.
  Your first visit (or coming back to find most of the slate unseen) starts the
  clock quietly rather than marking everything new.
- A new showing of a film you've **hidden** still surfaces — faded, with a **+** to
  bring the film back for good — so hiding "not right now" never permanently buries
  a film that comes back around. Ignore it and it slips away again next visit (and
  re-appears if it gets another new showing). Only the per-film hide is pierced this
  way; hiding a theater, weekday, or date is left alone.
- **IMDb ratings** (★) show next to films where known, and the **poster** links to
  IMDb. Each showing's **↗** opens that theater's showtimes/tickets page; theater
  names link to the theater's homepage. (IMDb links/ratings are resolved at build
  time with no API key; see the health/IMDb notes below.) Posters where available.
- Click the title (or "N theaters covered") to see every theater the page pulls
  from, with links — including ones currently filtered down to nothing.
- Light or dark theme follows your OS.
- **Add to calendar** exports whatever's currently showing (after your hides and
  theater filters) as an `.ics` file — built in your browser, no server. Import it
  into any calendar app. Showtimes are in Pacific (emitted as UTC so they land
  correctly anywhere); each is given a 2-hour default block since runtimes aren't
  in the source data.
- The page trims itself to today onward when you open it, so a page generated days
  ago still shows only upcoming showings.
- Hide things with the **×**: on a film (every showing of it disappears), by a
  theater's name (in "by theater"), by a date's heading (in "by date"), or a whole
  weekday via the chips below the controls. All are saved in your browser; the
  floating bar at the bottom tallies each kind and resets them. **⌘Z / Ctrl-Z**
  undoes your last hide (briefly flashing what came back); **⇧⌘Z / Ctrl-Y** redoes.
- Left open in a tab, the page auto-reloads when it's been regenerated, preserving
  your scroll. It's offline-safe: with no network it just keeps showing the cached
  page (it only reloads on a confirmed new build, never into a dead connection).
- A banner warns if a theater that usually has listings returned none this run
  (a likely sign its website changed) — see the health check below.

## Publishing

The page can be served at <https://dlowe.github.io/flicks/> from the `gh-pages`
branch:

- **From your machine (primary):** `./publish.sh` — builds and pushes `index.html`
  to `gh-pages` via a throwaway git worktree (the main tree is left untouched).
- **From CI:** `.github/workflows/publish.yml`, manual `workflow_dispatch` only.
  It's not on push/cron because GitHub's datacenter IPs get a Cloudflare 403 from
  Hollywood Theatre, so a CI-built page is missing Hollywood — publish locally
  (residential IP) for the full slate.

## Tuning what gets filtered

Edit **`filter.toml`** (then re-run `./run.sh`):

- `allow` — films to always keep (e.g. an old wide release shown as a revival).
- `deny` — films to always hide.
- `nonfilm_keywords` — substrings that mark non-film events (e.g. `"trivia"`).
- `wide_release_theater_count` / `dense_showings_per_day` — heuristic thresholds.
- `subtract_multiplex` — drop anything currently/soon playing at a big multiplex.

Each run prints a report of what was filtered and why, so you can see what to adjust.
`events.json` holds the full unfiltered listings if you want to inspect them.

## Health check

Each run records a per-theater fetch count in `health.json`. If a theater that
has produced listings before suddenly returns none — or its fetch errors — the
run flags it and the page shows a banner. That's the early warning that a
theater changed its website and its adapter needs attention. A theater that's
simply, legitimately empty right now (no history of listings) is not flagged.

## IMDb ratings & links

Done at build time, with no API key. Titles are matched to IMDb ids via IMDb's
keyless suggestion endpoint (disambiguated by year when the listing has one, and
only accepted on an exact title match to avoid wrong films), and ratings come from
IMDb's official `title.ratings.tsv.gz` dataset. Ids are cached in `imdb_ids.json`
and the ratings file is re-downloaded at most daily, so re-runs are fast. Title-only
matches can occasionally be wrong for generically-named films; feed-provided ids
(e.g. ForMovieTickets) are trusted over lookups.
