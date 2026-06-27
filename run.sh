#!/bin/bash
# Regenerate the calendar: fetch all theaters, rewrite events.json + index.html.
set -euo pipefail
cd "$(dirname "$0")"

# Ensure the venv exists and matches requirements.txt before building, so a
# dependency bump (after a git pull) can't silently run against stale or missing
# packages — important for the unattended publish. Only hits PyPI when
# requirements.txt is newer than the last install (or the venv is absent); a
# no-op on a steady-state machine.
stamp=".venv/.requirements-installed"
if [ ! -x .venv/bin/python ] || [ requirements.txt -nt "$stamp" ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
  touch "$stamp"
fi

exec ./.venv/bin/python -m flicks.main "$@"
