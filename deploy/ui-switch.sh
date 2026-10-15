#!/bin/bash
# The two interfaces /tv offers: the classic one (web/) and the new one (web-next/, built for /tv).
# Both stay installed; each device chooses in Settings (Interface), and devices that haven't chosen
# get the Pi's default.
#
#   ui-switch.sh build          (re)build the new interface under /opt/signal-tv-ui (deploy/install.sh
#                               runs this); the default is kept
#   ui-switch.sh setup          one time: install the /tv nginx snippet with the /tv/next/ routes (the new
#                               interface's artwork) and the method-map line for its gap reports
#   ui-switch.sh use new|classic   the default for devices that haven't chosen (instant, no restart)
#   ui-switch.sh status
#
# Layout:  /opt/signal-tv-ui/new -> new-<version>/             (web-next built by deploy/build_ui.py)
#          /opt/signal-tv-ui/classic -> /opt/signal-tv/web     (for reference; the app reads web/ itself)
#          /opt/signal-tv-ui/default -> new | classic
# The app (tvapp/server.py) reads these on every page load: nothing here needs a restart.
# `iptv ui new|classic|status` runs this script.
set -euo pipefail
# (paths and sudo can be overridden for tests/test_ui_switch.py; the defaults are the Pi's)
UI=${TV_UI_DIR:-/opt/signal-tv-ui}
APP=${TV_APP_DIR:-/opt/signal-tv}
SUDO=${TV_SUDO-sudo}
SNIPPET=${TV_UI_SNIPPET:-/etc/nginx/snippets/signal-tv.conf}
SITEMAP=${TV_UI_SITEMAP:-/etc/nginx/conf.d/10-site.conf}
MAPLINE='    "POST:/tv/next/api/art/gaps" 1;      # Signal TV: artwork-gap reports from the new interface (JSON only)'
SRC=$(cd "$(dirname "$0")/.." && pwd)

swap() {  # swap LINK TARGET: atomically point LINK at TARGET (rename(2) replaces the link, never follows it)
  $SUDO ln -sfn "$2" "$1.tmp"
  $SUDO python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$1.tmp" "$1"
}

build() {
  $SUDO install -d -m 0755 "$UI"                  # root-owned on the Pi (sudo)
  swap "$UI/classic" "$APP/web"
  local v prev
  v=$($SUDO python3 "$APP/deploy/build_ui.py" --base /tv "$UI/new-building")
  if [ -d "$UI/new-$v" ]; then $SUDO rm -rf "$UI/new-building"; else $SUDO mv "$UI/new-building" "$UI/new-$v"; fi
  prev=$(readlink "$UI/new" 2>/dev/null || true)
  swap "$UI/new" "new-$v"
  for d in "$UI"/new-*; do                            # keep this build and the one before it
    case "$(basename "$d")" in "new-$v"|"$prev") continue ;; esac
    $SUDO rm -rf "$d"
  done
  [ -L "$UI/default" ] || swap "$UI/default" classic
  echo "new interface built: new-$v; default for devices that haven't chosen: $(readlink "$UI/default")"
}

setup() {
  [ -e "$UI/new/index.html" ] || { echo "build first: $0 build (or deploy/install.sh)"; exit 1; }
  [ -e "$(dirname "$SNIPPET")/signal-tv-next-proxy.conf" ] || { echo "the sidecar proxy snippet is missing (deploy/tv-test/install-next.sh)"; exit 1; }
  local stamp b
  stamp=$(date -u +%Y%m%dT%H%M%SZ); b=/var/backups/nginx-tv-ui-$stamp
  $SUDO install -d -m 0700 "$b"
  $SUDO cp -a "$SNIPPET" "$SITEMAP" "$b/"
  # only ever add to the live snippet: refuse if it has lines the repo's copy lacks (an edit made on the Pi)
  if $SUDO diff "$SNIPPET" "$SRC/deploy/signal-tv.conf" | grep -q '^<'; then
    echo "$SNIPPET has changes that deploy/signal-tv.conf lacks - merge them first:"; $SUDO diff "$SNIPPET" "$SRC/deploy/signal-tv.conf" || true; exit 1
  fi
  $SUDO install -m 0644 "$SRC/deploy/signal-tv.conf" "$SNIPPET"
  $SUDO grep -qF '"POST:/tv/next/api/art/gaps"' "$SITEMAP" ||
    $SUDO sed -i "/\"~^POST:\/tv\/api\/state(\/import)?\$\" 1;/a\\$MAPLINE" "$SITEMAP"
  if ! $SUDO nginx -t 2>/dev/null; then
    $SUDO cp -a "$b/$(basename "$SNIPPET")" "$SNIPPET"; $SUDO cp -a "$b/$(basename "$SITEMAP")" "$SITEMAP"
    echo "nginx -t failed: both files restored from $b"; $SUDO nginx -t; exit 1
  fi
  $SUDO systemctl reload nginx
  echo "nginx updated (backup $b): /tv/next/ serves the new interface's artwork. Each device can now choose"
  echo "its interface in Settings; the default for the rest: iptv ui new|classic"
}

use() {
  local want=${1:-}
  [ "$want" = old ] && want=classic
  case "$want" in new|classic) ;; *) echo "usage: $0 use new|classic"; exit 2 ;; esac
  [ "$want" = classic ] || [ -e "$UI/new/index.html" ] || { echo "the new interface is not built: $0 build"; exit 1; }
  swap "$UI/default" "$want"
  echo "Devices that haven't chosen in Settings now get the $want interface (on their next page load)."
}

status() {
  echo "default:        $(readlink "$UI/default" 2>/dev/null || echo 'classic (not set)')  - for devices that haven't chosen in Settings"
  echo "new interface:  $(readlink "$UI/new" 2>/dev/null || echo 'not built')"
}

cmd=${1:-status}; shift || true
case "$cmd" in
  build) build ;;
  setup) setup ;;
  use) use "$@" ;;
  status) status ;;
  *) echo "usage: $0 build|setup|use new|classic|status"; exit 2 ;;
esac
