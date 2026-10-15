#!/bin/bash
# Install/update the /tv-test sidecar (tvnext) at /opt/signal-tv-next and (re)start it.
# Touches only /opt/signal-tv-next, signal-tv-next.service and its own state/cache directories:
# the live app (/opt/signal-tv, signal-tv.service, /var/lib/signal-tv) is not changed.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/opt/signal-tv-next
sudo -n mkdir -p "$DEST"
sudo -n rsync -rt --delete --exclude venv --exclude '__pycache__' --include 'tvapp/***' --include 'tvnext/***' \
  --include requirements.txt --include requirements-next.txt --exclude '*' "$SRC/" "$DEST/"
if [ ! -x "$DEST/venv/bin/python" ]; then sudo -n python3 -m venv "$DEST/venv"; fi
sudo -n "$DEST/venv/bin/pip" install -q --disable-pip-version-check -r "$DEST/requirements-next.txt"
sudo -n chown -R root:root "$DEST"
sudo -n install -m 0644 "$SRC/deploy/tv-test/signal-tv-next.service" /etc/systemd/system/signal-tv-next.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now signal-tv-next.service >/dev/null
sudo -n systemctl restart signal-tv-next.service
sleep 2
systemctl is-active signal-tv-next.service
curl -s http://127.0.0.1:8792/internal/status | head -c 600; echo
