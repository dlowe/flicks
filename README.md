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

## The page

- Showings grouped by day; each row links to the theater's page and shows the poster.
- Hover a film and click the **×** to hide it — every showing of that film disappears
  and stays hidden (saved in your browser). The bar at the bottom resets hidden films.

## Tuning what gets filtered

Edit **`filter.toml`** (then re-run `./run.sh`):

- `allow` — films to always keep (e.g. an old wide release shown as a revival).
- `deny` — films to always hide.
- `nonfilm_keywords` — substrings that mark non-film events (e.g. `"trivia"`).
- `wide_release_theater_count` / `dense_showings_per_day` — heuristic thresholds.
- `subtract_multiplex` — drop anything currently/soon playing at a big multiplex.

Each run prints a report of what was filtered and why, so you can see what to adjust.
`events.json` holds the full unfiltered listings if you want to inspect them.
