"""The internal key: proof that a request made straight to an app (not through nginx) comes from a program
on this machine that may make it - the artwork sidecar, `iptv`, the owner's app asking a family site,
tools/devproxy.py over an SSH tunnel.

Being on 127.0.0.1 is not that proof: any process on the Pi can connect there, with or without an
X-Forwarded-For header. So such a caller sends X-TV-Internal-Key. The TV services get the key through
systemd LoadCredential "tv-internal-key" (or TV_INTERNAL_KEY_FILE); `iptv` reads it with sudo. Without a
key configured nothing counts as internal.
"""
from __future__ import annotations

import functools
import hmac
import os
from pathlib import Path

HEADER = "x-tv-internal-key"


@functools.lru_cache(maxsize=4)
def _read(cred_dir: str | None, key_file: str | None) -> str | None:
    paths = [Path(cred_dir) / "tv-internal-key"] if cred_dir else []
    if key_file:
        paths.append(Path(key_file))
    for path in paths:
        try:
            key = path.read_text().strip()
        except OSError:
            continue
        if len(key) >= 32:
            return key
    return None


def key() -> str | None:
    return _read(os.environ.get("CREDENTIALS_DIRECTORY"), os.environ.get("TV_INTERNAL_KEY_FILE"))


def ok(request) -> bool:
    """A loopback request carrying exactly one copy of the right key."""
    k = key()
    if k is None or not request.client or request.client.host not in ("127.0.0.1", "::1"):
        return False
    sent = request.headers.getlist(HEADER)
    return len(sent) == 1 and hmac.compare_digest(sent[0].encode(), k.encode())


def headers() -> dict:
    """For calls this app makes to another one on this machine (never to anything outside)."""
    k = key()
    return {HEADER: k} if k else {}
