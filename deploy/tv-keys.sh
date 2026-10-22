#!/bin/bash
# Create (or keep) the two TV keys, root 0600; the key values never appear on a command line.
#   sudo deploy/tv-keys.sh        then: systemctl daemon-reload, reload nginx, restart the TV services
#
# /etc/signal-tv/internal-key         X-TV-Internal-Key: programs on this Pi calling an app directly (the sidecar,
#                                       iptv, the owner's app asking a family site, devproxy over SSH)
# /etc/signal-tv/site-proxy-key        X-Site-Proxy-Key: nginx proves a /tv request came through the central login;
#   + /etc/nginx/snippets/signal-tv-proxy-key.conf (the same value, for nginx)
# The services get them through systemd LoadCredential. Rotate: delete the file(s) and run this again.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
install -d -m 0750 -o root -g signal-tv /etc/signal-tv
python3 - <<'PY'
import os, secrets

def write(path, text):
    fd = os.open(path + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(path + ".new", path)
    os.chown(path, 0, 0)
    os.chmod(path, 0o600)

def key(path):
    try:
        k = open(path).read().strip()
    except FileNotFoundError:
        k = ""
    if len(k) < 32:
        k = secrets.token_urlsafe(48)
        write(path, k + "\n")
    os.chown(path, 0, 0)
    os.chmod(path, 0o600)
    return k

key("/etc/signal-tv/internal-key")
proxy = key("/etc/signal-tv/site-proxy-key")
write("/etc/nginx/snippets/signal-tv-proxy-key.conf", 'proxy_set_header X-Site-Proxy-Key "%s";\n' % proxy)
PY
echo "TV keys present (root 0600; the proxy key matches its nginx snippet)"
