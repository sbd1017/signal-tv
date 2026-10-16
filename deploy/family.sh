#!/bin/bash
# Family sites (tvapp/family.py): other households' copies of the app at their own address, each
# with its own provider, state and passphrase, all running this Pi's one copy of the code.
#
#   family.sh add NAME        create /NAME: settings files, its own service, the nginx snippet and
#                             method-map lines (nginx -t, both restored if it fails), its interface
#                             build; then it waits for a passphrase (Settings > Family sites on /tv,
#                             or `iptv family NAME passphrase`) and a provider (`iptv family NAME set-xtream`)
#   family.sh build [NAME…]   (re)build the new interface for each site (deploy/install.sh runs this)
#   family.sh remove NAME     take /NAME down for good: its service, nginx snippet and method-map line
#                             (nginx -t, restored if it fails), interface, settings (its provider file
#                             too), favourites/history and passphrase record
#   family.sh list            the sites, their service, provider and passphrase state
#   family.sh restart         restart every family site's service (after a deploy)
#
# Layout: /etc/signal-tv-family/NAME.site   TV_SITE, TV_BASE, TV_PORT (no secrets, 0644)
#         /etc/signal-tv-family/NAME.env    its provider (root:signal-tv 0640, like /etc/signal-tv/tv.env)
#         /opt/signal-tv-ui-NAME/new        its interface, built for /NAME (deploy/build_ui.py)
#         /var/lib/signal-tv/family/NAME.json   its passphrase record (written by the /tv app)
#         signal-tv-family@NAME.service; nginx snippets/signal-tv-family-NAME.conf
set -euo pipefail
# (paths and sudo can be overridden for tests/test_family_sh.py; the defaults are the Pi's)
FAM=${TV_FAMILY_DIR:-/etc/signal-tv-family}
APP=${TV_APP_DIR:-/opt/signal-tv}
UIROOT=${TV_UI_ROOT:-/opt}
SUDO=${TV_SUDO-sudo}
SNIPPETS=${TV_NGINX_SNIPPETS:-/etc/nginx/snippets}
SITEMAP=${TV_UI_SITEMAP:-/etc/nginx/conf.d/10-site.conf}
SYSTEMCTL=${TV_SYSTEMCTL:-systemctl}
NGINX=${TV_NGINX:-/usr/sbin/nginx}
SITES_AVAILABLE=${TV_NGINX_SITES:-/etc/nginx/sites-available}
UNITS=${TV_UNIT_DIR:-/etc/systemd/system}
BACKUPS=${TV_BACKUP_DIR:-/var/backups}
ENV_OWNER=${TV_ENV_OWNER-root:signal-tv}
FSTATE=${TV_FAMILY_STATE:-/var/lib/signal-tv-family}
FCACHE=${TV_FAMILY_CACHE:-/var/cache/signal-tv-family}
OWNER_STATE=${TV_OWNER_STATE:-/var/lib/signal-tv}
SRC=$(cd "$(dirname "$0")/.." && pwd)
RESERVED=" tv tv-test next new pwa static api m bets home media go convert pokemon admin login "
OWNER_MAP='    "~^POST:/tv/api/(family/[a-z0-9-]+/(passphrase|signout|provider)|tmdb|backup)$" 1;   # Signal TV: Settings > Family sites, TMDB key, backup provider'

add_map_line() {  # add_map_line LINE: into the site's method map, after the /tv state line (once)
  $SUDO python3 - "$SITEMAP" "$1" <<'PY'
import sys
path, line = sys.argv[1], sys.argv[2]
text = open(path).read()
anchor = '"~^POST:/tv/api/state(/import)?$" 1;'
if line.strip() not in text:
    i = text.index(anchor)
    j = text.index("\n", i) + 1
    open(path, "w").write(text[:j] + line + "\n" + text[j:])
PY
}

site_val() { sed -n "s/^$2=//p" "$FAM/$1.site" | head -1; }
names() { for f in "$FAM"/*.site; do [ -e "$f" ] && basename "$f" .site; done; return 0; }

swap() {  # swap LINK TARGET atomically
  $SUDO ln -sfn "$2" "$1.tmp"
  $SUDO python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$1.tmp" "$1"
}

build_one() {
  local name=$1 base ui v prev
  base=$(site_val "$name" TV_BASE)
  ui="$UIROOT/signal-tv-ui-$name"
  $SUDO install -d -m 0755 "$ui"
  v=$($SUDO python3 "$APP/deploy/build_ui.py" --base "$base" "$ui/new-building")
  if [ -d "$ui/new-$v" ]; then $SUDO rm -rf "$ui/new-building"; else $SUDO mv "$ui/new-building" "$ui/new-$v"; fi
  prev=$(readlink "$ui/new" 2>/dev/null || true)
  swap "$ui/new" "new-$v"
  swap "$ui/default" new
  for d in "$ui"/new-*; do
    case "$(basename "$d")" in "new-$v"|"$prev") continue ;; esac
    $SUDO rm -rf "$d"
  done
  echo "$name: interface built for $base (new-$v)"
}

build() {
  local list=("$@")
  [ ${#list[@]} -gt 0 ] || mapfile -t list < <(names)
  for n in "${list[@]}"; do build_one "$n"; done
}

nginx_install() {  # nginx_install NAME PORT: the snippet, the owner's include and the method-map lines; restored if nginx -t fails
  local name=$1 port=$2 stamp b snip="$SNIPPETS/signal-tv-family-$1.conf"
  stamp=$(date -u +%Y%m%dT%H%M%SZ); b=$BACKUPS/nginx-tv-family-$stamp
  $SUDO install -d -m 0700 "$b"
  $SUDO cp -a "$SITEMAP" "$SNIPPETS/signal-tv.conf" "$b/"
  # the owner's /tv snippet gains the include line; only ever add to it (refuse if it has edits the repo lacks)
  if $SUDO diff "$SNIPPETS/signal-tv.conf" "$SRC/deploy/signal-tv.conf" | grep -q '^<'; then
    echo "$SNIPPETS/signal-tv.conf has changes that deploy/signal-tv.conf lacks - merge them first"; exit 1
  fi
  $SUDO install -m 0644 "$SRC/deploy/signal-tv.conf" "$SNIPPETS/signal-tv.conf"
  sed -e "s/@NAME@/$name/g" -e "s/@PORT@/$port/g" "$SRC/deploy/signal-tv-family.conf" | $SUDO tee "$snip" >/dev/null
  $SUDO chmod 0644 "$snip"
  local line="    \"~^POST:/$name/(api/(state(/import)?|login|logout)|next/api/art/gaps)\$\" 1;   # Signal TV family site $name"
  $SUDO grep -qF "POST:/$name/" "$SITEMAP" || add_map_line "$line"
  # the owner's Settings line: added once, replaced when the repo's version changes (new actions)
  if ! $SUDO grep -qF "$OWNER_MAP" "$SITEMAP"; then
    $SUDO grep -qE 'POST:/tv/api/(\(?family)' "$SITEMAP" && $SUDO python3 -c 'import re, sys; p = sys.argv[1]; t = open(p).read().splitlines(True); open(p, "w").writelines(l for l in t if not re.search(r"POST:/tv/api/\(?family", l))' "$SITEMAP"
    add_map_line "$OWNER_MAP"
  fi
  if ! $SUDO "$NGINX" -t 2>/dev/null; then
    $SUDO cp -a "$b/$(basename "$SITEMAP")" "$SITEMAP"; $SUDO cp -a "$b/signal-tv.conf" "$SNIPPETS/signal-tv.conf"; $SUDO rm -f "$snip"
    echo "nginx -t failed: restored from $b"; $SUDO "$NGINX" -t; exit 1
  fi
  $SUDO "$SYSTEMCTL" reload nginx
  echo "nginx: /$name/ added (backup $b)"
}

add() {
  local name=${1:-} port used
  [[ "$name" =~ ^[a-z0-9][a-z0-9-]{1,29}$ ]] || { echo "usage: family.sh add NAME (lower case letters, digits, -)"; exit 2; }
  case "$RESERVED" in *" $name "*) echo "/$name is taken by something else on the site"; exit 1 ;; esac
  [ ! -e "$FAM/$name.site" ] || { echo "$name exists already (family.sh list)"; exit 1; }
  if $SUDO grep -rqsE "location[^{]*[ =^~]/$name(/|[ {]|\$)" "$SITES_AVAILABLE" "$SNIPPETS" 2>/dev/null; then
    echo "/$name is already used on the site (nginx has a location for it)"; exit 1
  fi
  # the first free port from 8793 (8790 /tv, 8791 demo provider, 8792 artwork sidecar)
  used=" $( (cat "$FAM"/*.site 2>/dev/null || true) | sed -n 's/^TV_PORT=//p' | tr '\n' ' ') "
  port=8793
  while [[ "$used" == *" $port "* ]] || ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; do port=$((port + 1)); done
  $SUDO install -d -m 0755 "$FAM"
  printf 'TV_SITE=%s\nTV_BASE=/%s\nTV_PORT=%s\n' "$name" "$name" "$port" | $SUDO tee "$FAM/$name.site" >/dev/null
  $SUDO chmod 0644 "$FAM/$name.site"
  if [ ! -e "$FAM/$name.env" ]; then
    $SUDO install -m 0640 "$SRC/tv.env.example" "$FAM/$name.env"
    [ -z "$ENV_OWNER" ] || $SUDO chown "$ENV_OWNER" "$FAM/$name.env"
  fi
  $SUDO install -m 0644 "$SRC/deploy/signal-tv-family@.service" "$UNITS/signal-tv-family@.service"
  $SUDO "$SYSTEMCTL" daemon-reload
  build_one "$name"
  nginx_install "$name" "$port"
  $SUDO "$SYSTEMCTL" enable --now "signal-tv-family@$name.service" >/dev/null
  # the artwork sidecar learns the new address (/NAME/next/) when it starts
  $SUDO "$SYSTEMCTL" try-restart signal-tv-next.service || true
  echo "family site $name: https://example.com/$name/ (port $port)"
  echo "  next: set its provider  -> iptv family $name set-xtream   (or set-playlist / use-demo)"
  echo "        set a passphrase  -> Settings > Family sites on /tv, or iptv family $name passphrase"
}

remove() {
  local name=${1:-} stamp b snip
  [[ "$name" =~ ^[a-z0-9][a-z0-9-]{1,29}$ ]] && [ -e "$FAM/$name.site" ] || { echo "no family site called ${name:-?} (family.sh list)"; exit 1; }
  $SUDO "$SYSTEMCTL" disable --now "signal-tv-family@$name.service" >/dev/null 2>&1 || true
  snip="$SNIPPETS/signal-tv-family-$name.conf"
  stamp=$(date -u +%Y%m%dT%H%M%SZ); b=$BACKUPS/nginx-tv-family-$stamp
  $SUDO install -d -m 0700 "$b"
  $SUDO cp -a "$SITEMAP" "$b/"
  [ ! -e "$snip" ] || $SUDO cp -a "$snip" "$b/"
  $SUDO rm -f "$snip"
  $SUDO python3 - "$SITEMAP" "$name" <<'PY'
import sys
path, name = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines(keepends=True)
open(path, "w").write("".join(l for l in lines if f'"~^POST:/{name}/(' not in l))
PY
  if ! $SUDO "$NGINX" -t 2>/dev/null; then
    $SUDO cp -a "$b/$(basename "$SITEMAP")" "$SITEMAP"; [ ! -e "$b/$(basename "$snip")" ] || $SUDO cp -a "$b/$(basename "$snip")" "$snip"
    $SUDO "$SYSTEMCTL" enable --now "signal-tv-family@$name.service" >/dev/null 2>&1 || true
    echo "nginx -t failed: restored from $b, $name left running"; $SUDO "$NGINX" -t; exit 1
  fi
  $SUDO "$SYSTEMCTL" reload nginx
  $SUDO rm -rf "$UIROOT/signal-tv-ui-$name" "$FSTATE/$name" "$FCACHE/$name"
  $SUDO rm -f "$FAM/$name.site" "$FAM/$name.env" "$OWNER_STATE/family/$name.json"
  $SUDO "$SYSTEMCTL" try-restart signal-tv-next.service || true      # the sidecar forgets /NAME/next/
  echo "family site $name removed (nginx backup $b)"
}

list() {
  local any=0
  for n in $(names); do
    any=1
    printf '%-12s %-14s port %-5s %s\n' "$n" "$(site_val "$n" TV_BASE)" "$(site_val "$n" TV_PORT)" "$($SYSTEMCTL is-active "signal-tv-family@$n" 2>/dev/null || true)"
  done
  [ $any = 1 ] || echo "no family sites (iptv family add NAME)"
}

restart() {
  for n in $(names); do $SUDO "$SYSTEMCTL" restart "signal-tv-family@$n.service" && echo "$n restarted"; done
}

cmd=${1:-list}; shift || true
case "$cmd" in
  add) add "$@" ;;
  remove) remove "$@" ;;
  build) build "$@" ;;
  list) list ;;
  restart) restart ;;
  *) echo "usage: $0 add NAME | remove NAME | build [NAME…] | list | restart"; exit 2 ;;
esac
