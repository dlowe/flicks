#!/bin/bash
# Install (or reinstall) the LaunchAgent that builds + publishes flicks daily.
# A per-user agent, so it runs in your logged-in GUI session with your network
# and SSH credentials. launchd runs a scheduled run missed during sleep when the
# machine next wakes — so on a mostly-asleep, used-most-days laptop it publishes
# shortly after you next open the lid. (macOS only.)
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd -P)"
LABEL="com.dlowe.flicks.publish"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__FLICKS_DIR__|$DIR|g" "launchd/$LABEL.plist" > "$DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true   # unload if already present
launchctl bootstrap "gui/$(id -u)" "$DEST"

echo "Installed $DEST (publishes daily ~09:00, or on next wake if asleep then)."
echo
echo "  Run now:   launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "  Logs:      tail -f $DIR/.publish.log"
echo "  Status:    launchctl print gui/$(id -u)/$LABEL | grep -i state"
echo "  Uninstall: launchctl bootout gui/$(id -u)/$LABEL && rm $DEST"
echo
echo "First time: run it once (kickstart) and check the log actually pushes —"
echo "that confirms your SSH key is reachable non-interactively."
