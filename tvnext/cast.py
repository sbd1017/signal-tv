"""Cast in the player, from TMDB (themoviedb.org): who is in a film, or in an episode (its regulars and
guest stars), with their character and photo. Optional: it needs the owner's own free TMDB API key,
entered in Settings (or `iptv set-tmdb`) and kept here on the Pi, never in the code.

Titles are found by the TMDB number the provider gives (Xtream: tmdb_id / tmdb); without one, by a
search on the exact title and year, used only when exactly one result fits. Answers are kept for 30
days (a miss for 7), so a title is looked up once however many devices play it. Photos are fetched
from TMDB's image host only, kept on disk and served from the Pi like the rest of the artwork.

TMDB's terms ask for credit: the page says "This product uses the TMDB API but is not endorsed or
certified by TMDB" wherever the cast is offered.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import httpx

from . import config

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
PHOTO = re.compile(r"^/?([A-Za-z0-9]{8,48}\.(?:jpg|png))$")
SIZES = ("w185",)
KEEP_DAYS, MISS_DAYS = 30, 7
MAX_MAIN, MAX_GUESTS = 14, 12
CREDIT = "This product uses the TMDB API but is not endorsed or certified by TMDB."


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def key_kind(key: str) -> str | None:
    """A v3 API key (32 hex) or a v4 read access token (a JWT); anything else isn't a key."""
    key = (key or "").strip()
    if re.fullmatch(r"[0-9a-f]{32}", key):
        return "v3"
    if re.fullmatch(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", key) and len(key) < 2000:
        return "v4"
    return None


class Cast:
    def __init__(self, client: httpx.AsyncClient, state: Path | None = None, cache: Path | None = None):
        self.client = client
        self.state = state or config.STATE
        self.cache = (cache or config.CACHE) / "cast-img"
        self.dir = self.state / "cast"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.keyfile = self.state / "tmdb.json"
        self._key: tuple | None = None
        self.locks: dict[str, asyncio.Lock] = {}

    # ---------------------------------------------------------------- the key
    def key(self) -> dict | None:
        try:
            st = self.keyfile.stat()
        except OSError:
            self._key = None
            return None
        if not self._key or self._key[0] != st.st_mtime_ns:
            try:
                rec = json.loads(self.keyfile.read_text())
            except (OSError, ValueError):
                rec = {}
            self._key = (st.st_mtime_ns, rec if key_kind(rec.get("key", "")) else None)
        return self._key[1]

    def status(self) -> dict:
        rec = self.key()
        return {"on": bool(rec), "kind": rec.get("kind") if rec else None, "set": rec.get("set", 0) if rec else 0, "credit": CREDIT}

    def _auth(self, rec: dict) -> tuple[dict, dict]:
        if rec["kind"] == "v4":
            return {"Authorization": f"Bearer {rec['key']}", "Accept": "application/json"}, {}
        return {"Accept": "application/json"}, {"api_key": rec["key"]}

    async def check_key(self, key: str) -> str:
        """'' when TMDB accepts the key, else what's wrong (in words for the Settings page)."""
        kind = key_kind(key)
        if not kind:
            return "That doesn't look like a TMDB key: use the API Key (32 letters and digits) or the API Read Access Token."
        headers, params = self._auth({"key": key.strip(), "kind": kind})
        try:
            r = await self.client.get(f"{API}/configuration", headers=headers, params=params, timeout=15)
        except httpx.HTTPError as e:
            return f"Couldn't reach TMDB ({type(e).__name__}). Try again in a moment."
        if r.status_code == 401:
            return "TMDB refused that key. Copy it again from themoviedb.org › Settings › API."
        if r.status_code != 200:
            return f"TMDB answered HTTP {r.status_code}."
        return ""

    def save_key(self, key: str) -> None:
        key = (key or "").strip()
        if not key:
            self.keyfile.unlink(missing_ok=True)
            self._key = None
            return
        tmp = self.keyfile.with_suffix(f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"key": key, "kind": key_kind(key), "set": int(time.time())}, fh)
        os.replace(tmp, self.keyfile)
        self._key = None

    # ---------------------------------------------------------------- lookups
    async def _get(self, rec: dict, path: str, **params) -> dict | None:
        headers, auth = self._auth(rec)
        r = await self.client.get(f"{API}{path}", headers=headers, params={**auth, **params}, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def _find(self, rec: dict, kind: str, title: str, year: int) -> int:
        """A title without the provider's TMDB number: the one search result with this exact title (and year)."""
        want = fold(title)
        if not want:
            return 0
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year" if kind == "movie" else "first_air_date_year"] = str(year)
        d = await self._get(rec, f"/search/{kind}", **params) or {}
        hits = []
        for x in d.get("results") or []:
            names = {fold(x.get("title") or x.get("name") or ""), fold(x.get("original_title") or x.get("original_name") or "")}
            date = x.get("release_date") or x.get("first_air_date") or ""
            if want in names and (not year or date[:4] == str(year)):
                hits.append(x["id"])
        return hits[0] if len(hits) == 1 else 0

    @staticmethod
    def _people(lst, guest=False) -> list[dict]:
        out = []
        for p in lst or []:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            role = p.get("character") or ""
            if not role and p.get("roles"):                       # aggregate_credits: one entry, several roles
                role = (p["roles"][0] or {}).get("character") or ""
            m = PHOTO.match(p.get("profile_path") or "")
            out.append({"name": str(p["name"])[:80], "character": re.sub(r"\s*\(voice\)\s*$", "", str(role))[:80],
                        "photo": m.group(1) if m else "", "guest": guest})
        return out

    async def lookup(self, kind: str, tmdb: int, title: str, year: int, season: int, episode: int) -> dict:
        rec = self.key()
        if not rec:
            return {"cast": None, "reason": "off"}
        name = f"{kind}-{tmdb or 'q'}-{season}-{episode}-" + hashlib.sha1(f"{fold(title)}|{year}".encode()).hexdigest()[:10]
        path = self.dir / f"{name}.json"
        try:
            hit = json.loads(path.read_text())
            if time.time() - hit["at"] < (KEEP_DAYS if hit.get("cast") else MISS_DAYS) * 86400:
                return hit
        except (OSError, ValueError, KeyError):
            pass
        lock = self.locks.setdefault(name, asyncio.Lock())
        async with lock:
            try:
                tid = tmdb or await self._find(rec, kind, title, year)
                cast: list[dict] = []
                if tid and kind == "movie":
                    d = await self._get(rec, f"/movie/{tid}/credits") or {}
                    cast = self._people(d.get("cast"))[:MAX_MAIN]
                elif tid:
                    d = None
                    if season and episode:
                        d = await self._get(rec, f"/tv/{tid}/season/{season}/episode/{episode}/credits")
                    if d:
                        cast = self._people(d.get("cast"))[:MAX_MAIN] + self._people(d.get("guest_stars"), True)[:MAX_GUESTS]
                    if not cast:
                        d = await self._get(rec, f"/tv/{tid}/aggregate_credits") or {}
                        cast = self._people(d.get("cast"))[:MAX_MAIN]
            except (httpx.HTTPError, ValueError) as e:
                return {"cast": None, "reason": f"TMDB unavailable ({type(e).__name__})"}
            out = {"at": int(time.time()), "tmdb": tid, "cast": cast or None, "credit": CREDIT}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False))
            os.replace(tmp, path)
            self.locks.pop(name, None)
            return out

    # ---------------------------------------------------------------- photos
    async def photo(self, size: str, file: str) -> Path | None:
        if size not in SIZES or not PHOTO.match(file):
            return None
        p = self.cache / f"{size}-{file}"
        if p.exists():
            return p
        r = await self.client.get(f"{IMG}/{size}/{file}", timeout=20)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/") or len(r.content) > 2_000_000:
            return None
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        os.replace(tmp, p)
        return p
