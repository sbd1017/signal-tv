"""Family sites: extra copies of the app for other households (each with its own provider, state and
address, e.g. /mumtv), protected by one passphrase that the owner sets and changes - also remotely,
from the owner's own Settings page (Family sites).

Pieces:
- A family site runs with TV_AUTH=passphrase, TV_BASE=/<name>, TV_ACCESS_FILE=<record>. It shows a
  passphrase page until a device signs in; the session cookie carries the record's generation, so a
  new passphrase or "sign everyone out" (generation + 1) ends every session at once.
- The record (<owner state>/family/<name>.json, written only by the owner's app or `iptv family`) holds
  a scrypt hash of the passphrase, never the passphrase itself.
- The owner's app finds the sites in <family_dir>/<name>.site (TV_SITE, TV_BASE, TV_PORT; no secrets)
  and asks each one's health on loopback.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
MIN_LEN, MAX_LEN = 6, 128
_N, _R, _P = 2 ** 14, 8, 1                  # scrypt cost: ~50 ms on a Pi 5


# ------------------------------------------------------------------ the passphrase record
def hash_passphrase(passphrase: str) -> dict:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(passphrase.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return {"alg": "scrypt", "n": _N, "r": _R, "p": _P, "salt": salt.hex(), "hash": h.hex()}


def verify(record: dict | None, passphrase: str) -> bool:
    try:
        rec = (record or {})["pass"]
        h = hashlib.scrypt(passphrase.encode(), salt=bytes.fromhex(rec["salt"]), n=rec["n"], r=rec["r"], p=rec["p"], dklen=32)
        return hmac.compare_digest(h.hex(), rec["hash"])
    except (KeyError, TypeError, ValueError):
        return False


def check_passphrase(passphrase: str) -> str | None:
    """Why this passphrase can't be used, or None."""
    if not isinstance(passphrase, str) or len(passphrase.strip()) < MIN_LEN:
        return f"Use at least {MIN_LEN} characters."
    if len(passphrase) > MAX_LEN:
        return f"Use at most {MAX_LEN} characters."
    return None


def read_record(path: Path) -> dict:
    try:
        rec = json.loads(path.read_text())
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        return {}


def write_record(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(rec, fh)
    os.replace(tmp, path)


def set_passphrase(path: Path, passphrase: str) -> dict:
    """New passphrase: every signed-in device is signed out (generation + 1)."""
    rec = read_record(path)
    rec = {"pass": hash_passphrase(passphrase), "gen": int(rec.get("gen", 0)) + 1, "changed": int(time.time()),
           "signed_out": int(time.time())}
    write_record(path, rec)
    return rec


def sign_out_all(path: Path) -> dict:
    rec = read_record(path)
    rec["gen"] = int(rec.get("gen", 0)) + 1
    rec["signed_out"] = int(time.time())
    write_record(path, rec)
    return rec


class Access:
    """A family site's view of its record: re-read when the file changes (the owner's app writes it)."""

    def __init__(self, path: Path | None):
        self.path = path
        self._stamp: tuple | None = None
        self._rec: dict = {}

    def record(self) -> dict:
        if not self.path:
            return {}
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self._stamp, self._rec = None, {}
            return {}
        if stamp != self._stamp:
            self._stamp, self._rec = stamp, read_record(self.path)
        return self._rec

    def gen(self) -> int:
        return int(self.record().get("gen", 0)) + 1      # never 0: 0 is the owner's own (nginx) cookie

    def is_set(self) -> bool:
        return "pass" in self.record()

    def verify(self, passphrase: str) -> bool:
        return verify(self.record(), passphrase)


# ------------------------------------------------------------------ guessing
class Throttle:
    """Wrong passphrases: 5 per address per 15 minutes, 40 per site per hour, then a wait."""

    def __init__(self, per_ip: int = 5, ip_window: int = 900, per_site: int = 40, site_window: int = 3600, clock=time.time):
        self.per_ip, self.ip_window, self.per_site, self.site_window, self.clock = per_ip, ip_window, per_site, site_window, clock
        self.fails: dict[str, list[float]] = {}
        self.site: list[float] = []

    def blocked(self, ip: str) -> bool:
        now = self.clock()
        self.site = [t for t in self.site if now - t < self.site_window]
        mine = [t for t in self.fails.get(ip, []) if now - t < self.ip_window]
        self.fails[ip] = mine
        return len(mine) >= self.per_ip or len(self.site) >= self.per_site

    def failed(self, ip: str) -> None:
        now = self.clock()
        self.fails.setdefault(ip, []).append(now)
        self.site.append(now)
        if len(self.fails) > 5000:                       # forget the oldest addresses
            for k in sorted(self.fails, key=lambda k: max(self.fails[k] or [0]))[:2500]:
                del self.fails[k]

    def passed(self, ip: str) -> None:
        self.fails.pop(ip, None)


# ------------------------------------------------------------------ the owner's side
def read_env(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def sites(family_dir: Path) -> list[dict]:
    """[{name, base, port}] from <family_dir>/<name>.site."""
    out = []
    try:
        files = sorted(family_dir.glob("*.site"))
    except OSError:
        return out
    for f in files:
        env = read_env(f)
        name = env.get("TV_SITE", f.stem)
        try:
            port = int(env.get("TV_PORT", "0"))
        except ValueError:
            continue
        if NAME.match(name) and 1024 < port < 65536:
            out.append({"name": name, "base": env.get("TV_BASE", f"/{name}"), "port": port})
    return out


def record_path(state_dir: Path, name: str) -> Path:
    if not NAME.match(name):
        raise ValueError("not a site name")
    return state_dir / "family" / f"{name}.json"


# ------------------------------------------------------------------ iptv family NAME passphrase|signout|clear
def main(argv=None) -> int:
    """Run as the app's user (iptv does: sudo -u signal-tv). The passphrase comes on stdin, never argv."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="iptv family NAME")
    ap.add_argument("action", choices=["passphrase", "signout", "clear", "state"])
    ap.add_argument("name")
    a = ap.parse_args(argv)
    state = Path(os.environ.get("TV_STATE_DIR", "/var/lib/signal-tv"))
    path = record_path(state, a.name)
    if a.action == "passphrase":
        phrase = sys.stdin.readline().rstrip("\n")
        problem = check_passphrase(phrase)
        if problem:
            print(problem, file=sys.stderr)
            return 2
        set_passphrase(path, phrase)
        print(f"{a.name}: new passphrase set; every device there signs in again")
    elif a.action == "signout":
        sign_out_all(path)
        print(f"{a.name}: everyone signed out")
    elif a.action == "clear":
        path.unlink(missing_ok=True)
        print(f"{a.name}: passphrase removed - nobody can open it until a new one is set")
    else:
        rec = read_record(path)
        print(f"{a.name}: passphrase {'set ' + time.strftime('%Y-%m-%d %H:%M', time.localtime(rec['changed'])) if 'pass' in rec else 'not set'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
