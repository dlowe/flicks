# flicks

A combined calendar of what's playing at Portland's indie & repertory movie
theaters — built locally, with wide releases and non-film events filtered out.
The output is a single self-contained webpage.

## First-time setup

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

- **By date / by film / by theater** toggle at the top (your choice is remembered).
  "By theater" lists each film once per theater with all its dates.
- Each showing's **🔗** opens that theater's showtimes/tickets page; theater names
  link to the theater's homepage; and where an IMDb id is known, the **poster**
  links to IMDb. Posters are shown where available.
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
  floating bar at the bottom tallies each kind and resets them.
- Left open in a tab, the page auto-reloads when it's been regenerated (and falls
  back to a slow timed reload if it can't poll the file), preserving your scroll.
- A banner warns if a theater that usually has listings returned none this run
  (a likely sign its website changed) — see the health check below.

## Publishing

The page can be served at <https://dlowe.github.io/flicks/> from the `gh-pages`
branch:

- **From your machine:** `./publish.sh` — builds and pushes `index.html` to
  `gh-pages` via a throwaway git worktree (the main tree is left untouched).
- **From CI:** `.github/workflows/publish.yml` rebuilds and publishes on every push
  to `main`, plus a weekly cron, plus manual `workflow_dispatch`.

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
