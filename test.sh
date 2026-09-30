#!/bin/bash
# Run the client-logic tests: "new to you"/leaks, touch UI, and the offline
# guarantees. Pure node, no deps — drives the real in-page scripts from the
# template (and sw.js) with fixture data.
set -euo pipefail
cd "$(dirname "$0")"
status=0
for t in tests/*.test.js; do
  echo "# $t"
  node "$t" || status=1
done
exit $status
