#!/bin/bash
# Regenerate the calendar: fetch all theaters, rewrite events.json + index.html.
cd "$(dirname "$0")"
exec ./.venv/bin/python -m flicks.main "$@"
