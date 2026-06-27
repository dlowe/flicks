#!/bin/bash
# Build the page locally and publish it to the gh-pages branch, served at
# https://dlowe.github.io/flicks/. The main working tree is left untouched —
# we stage the output through a throwaway git worktree on gh-pages.
set -euo pipefail
cd "$(dirname "$0")"

./run.sh

work="$(mktemp -d)"
trap 'git worktree remove --force "$work" 2>/dev/null || true; rm -rf "$work"' EXIT

# Always build on top of the *latest published* page. gh-pages is also pushed
# from CI and other machines, so this laptop's local gh-pages branch is often
# behind. Basing the worktree on origin/gh-pages (not the local branch) keeps the
# push a fast-forward instead of a reject, and never clobbers a newer publish.
git fetch origin gh-pages 2>/dev/null || true
if git show-ref --verify --quiet refs/remotes/origin/gh-pages; then
  git worktree add --force --detach "$work" origin/gh-pages
else
  git worktree add --force --orphan -b gh-pages "$work"
fi

assets="index.html events.json manifest.webmanifest icon.svg apple-touch-icon.png icon-192.png icon-512.png"
cp $assets "$work/"
git -C "$work" add $assets
git -C "$work" commit -m "Publish $(date -u +%Y-%m-%dT%H:%MZ)" \
  && git -C "$work" push origin HEAD:gh-pages \
  || echo "Nothing new to publish."

echo "Done. https://dlowe.github.io/flicks/"
