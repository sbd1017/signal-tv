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


# ------------------------------------------------------------------ the provider, set from the owner's Settings
# The owner's app forwards the form to the family site on loopback; the site checks the details with
# the provider first and only then keeps them (<its state>/provider.env, 0600; tvapp/config.py prefers
# whichever of that and its TV_CONFIG was saved last). Nothing here ever logs or returns the details.
def parse_provider(body: dict) -> tuple[dict | None, str]:
    """The form -> config values, or (None, why not). An Xtream "get.php?username=…&password=…" link
    pasted as a playlist is kept as the Xtream account it is (films and series come with it)."""
    from urllib.parse import parse_qs, urlsplit
    if not isinstance(body, dict):
        return None, "Nothing to save."
    kind = body.get("type")
    clean = lambda k: str(body.get(k) or "").strip()                     # noqa: E731
    if any("\n" in clean(k) or "\r" in clean(k) for k in ("base", "username", "password", "url")):
        return None, "One line per field, please."
    if kind == "m3u":
        url = clean("url")
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname or len(url) > 2000:
            return None, "Paste the whole playlist link, starting with http:// or https://."
        q = parse_qs(u.query)
        if u.path.rstrip("/").endswith("get.php") and q.get("username") and q.get("password"):
            return {"IPTV_PROVIDER_TYPE": "xtream", "XTREAM_BASE_URL": f"{u.scheme}://{u.netloc}",
                    "XTREAM_USERNAME": q["username"][0], "XTREAM_PASSWORD": q["password"][0]}, ""
        return {"IPTV_PROVIDER_TYPE": "m3u", "IPTV_M3U_URL": url}, ""
    if kind == "xtream":
        base, user, pw = clean("base").rstrip("/"), clean("username"), clean("password")
        if base and "://" not in base:
            base = "http://" + base
        u = urlsplit(base)
        if u.scheme not in ("http", "https") or not u.hostname:
            return None, "The server address should look like http://example.com:8080."
        if not user or not pw:
            return None, "Fill in the username and password."
        return {"IPTV_PROVIDER_TYPE": "xtream", "XTREAM_BASE_URL": f"{u.scheme}://{u.netloc}", "XTREAM_USERNAME": user,
                "XTREAM_PASSWORD": pw}, ""
    return None, "Choose an Xtream account or a playlist link."


async def check_provider(http, values: dict, user_agent: str) -> tuple[str, dict]:
    """Ask the provider before keeping the details: ("", info) when it accepts them, else (what's wrong, {})."""
    import httpx
    from urllib.parse import urlsplit
    xtream = values["IPTV_PROVIDER_TYPE"] == "xtream"
    url = values["XTREAM_BASE_URL"] + "/player_api.php" if xtream else values["IPTV_M3U_URL"]
    u = urlsplit(url)
    where = f"{u.hostname}:{u.port or (443 if u.scheme == 'https' else 80)}"
    params = {"username": values["XTREAM_USERNAME"], "password": values["XTREAM_PASSWORD"]} if xtream else None
    try:
        async with http.stream("GET", url, params=params, headers={"User-Agent": user_agent},
                               timeout=httpx.Timeout(15, read=40)) as r:
            head = b""
            async for chunk in r.aiter_bytes():
                head += chunk
                if len(head) > 65536:
                    break
            code = r.status_code
    except httpx.ConnectError:
        return f"Couldn't connect to {where}. Check the address and the port (many providers use :8080).", {}
    except httpx.TimeoutException:
        return f"{where} didn't answer in time. Check the address, or try again later.", {}
    except httpx.HTTPError as e:
        return f"Couldn't reach {where} ({type(e).__name__}).", {}
    low = head[:400].lower()
    if code == 400 and b"hostname" in low:
        return "The provider's server doesn't recognise that address. Use the exact server URL from the provider's details.", {}
    if code in (401, 403) or (xtream and code == 200 and b'"auth":0' in head.replace(b" ", b"")):
        return "The provider refused that username and password.", {}
    if code == 404:
        return "Nothing at that address (404). Check the link or server URL.", {}
    if code != 200:
        return f"The provider answered HTTP {code}.", {}
    if not xtream:
        if not head.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U"):
            return "That link didn't return a playlist (no #EXTM3U at the start).", {}
        return "", {"type": "m3u"}
    try:
        ui = json.loads(head).get("user_info") or {}
    except ValueError:
        return "That address answered, but not as an Xtream server. Check the server URL.", {}
    if str(ui.get("auth")) != "1":
        return "The provider refused that username and password.", {}
    status = str(ui.get("status") or "")
    if status and status.lower() != "active":
        return f"The provider says the account is {status.lower()}.", {}
    try:
        exp = int(ui.get("exp_date") or 0)
    except (TypeError, ValueError):
        exp = 0
    return "", {"type": "xtream", "expires": exp, "connections": ui.get("max_connections")}


def write_provider(state_dir: Path, values: dict) -> Path:
    path = state_dir / "provider.env"
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("# set from the owner's Settings > Family sites; `iptv family NAME set-…` saved later wins\n")
        for k, v in values.items():
            fh.write(f"{k}={v}\n")
    os.replace(tmp, path)
    return path


def provider_summary(s) -> dict:
    """What the owner sees: the kind, the port, where it was set and when - never the details."""
    from urllib.parse import urlsplit
    url = s.xtream_base if s.provider_type == "xtream" else s.m3u_url
    u = urlsplit(url) if url else None
    src = (s.state_dir / "provider.env") if s.provider_source == "web" else Path(os.environ.get("TV_CONFIG", ""))
    try:
        changed = int(src.stat().st_mtime)
    except OSError:
        changed = 0
    return {"type": s.provider_type, "configured": s.configured, "port": (u.port or (443 if u.scheme == "https" else 80)) if u else None,
            "source": s.provider_source, "changed": changed}


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
