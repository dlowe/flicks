#!/bin/bash
# Run the client-logic tests (the "new to you" / leak behavior). Pure node, no
# deps — drives the real in-page script from the template with fixture data.
set -euo pipefail
cd "$(dirname "$0")"
node tests/seen.test.js
