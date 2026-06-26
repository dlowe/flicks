#!/bin/bash
# Dev convenience: rebuild index.html from the cached events.json + multiplex.json
# without re-fetching any theater. Run ./run.sh at least once first to populate
# the caches. Use this while iterating on filtering or the page template.
cd "$(dirname "$0")"
exec ./.venv/bin/python -m flicks.main --render-only "$@"
