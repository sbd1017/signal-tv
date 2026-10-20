"""Backup providers: a second subscription the app falls back to when the main one won't play a channel.

The catalogue stays the main provider's. For each backup only its live channels are indexed (kept small:
stream id, name, guide id, url), refreshed with the catalogue. A channel the main provider won't start -
or that the viewer switches by hand ("Switch provider" in the player) - is played from the backup's same
channel, found by:
  1. the same stream id with the same name (two logins on one service share their channel ids),
  2. the same guide (EPG) id, when exactly one channel has it,
  3. the same name once quality words and markers are set aside (HD / FHD / 4K / RAW / ◉ ...), when one fits.

Settings: <state>/backups.json (0600), written by the owner's Settings › Providers (checked with the
provider first, tvapp/family.py) and never shown back. Films and series come in a later step.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

import httpx

from . import providers
from .config import Settings
from .util import iter_json_array

log = logging.getLogger("tv")
KEYS = ("IPTV_PROVIDER_TYPE", "IPTV_M3U_URL", "XTREAM_BASE_URL", "XTREAM_USERNAME", "XTREAM_PASSWORD")
QUALITY = re.compile(r"\b(uhd|fhd|hd|sd|4k|8k|raw|hevc|h265|50fps|60fps|vip|backup)\b")
MARKS = re.compile(r"[^\w\s:|]+")


def norm_name(name: str) -> str:
    """'UK: SKY SPORTS MAIN EVENT ᴴᴰ ◉' -> 'uk sky sports main event'."""
    t = unicodedata.normalize("NFKC", name or "").lower()
    t = MARKS.sub(" ", t)
    t = QUALITY.sub(" ", t)
    return re.sub(r"[\s:|]+", " ", t).strip()


def path_for(state_dir: Path) -> Path:
    return state_dir / "backups.json"


def load(state_dir: Path) -> list[dict]:
    try:
        rows = json.loads(path_for(state_dir).read_text())
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("IPTV_PROVIDER_TYPE") in ("xtream", "m3u")][:3]


def save(state_dir: Path, rows: list[dict]) -> None:
    p = path_for(state_dir)
    if not rows:
        p.unlink(missing_ok=True)
        return
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump([{k: r[k] for k in KEYS if k in r} | {"label": r.get("label", "Backup")} for r in rows], fh)
    os.replace(tmp, p)


class Backup:
    def __init__(self, base: Settings, row: dict, index: int):
        self.label = row.get("label") or f"Backup {index + 1}"
        self.settings = dataclasses.replace(
            base, provider_type=row["IPTV_PROVIDER_TYPE"], m3u_url=row.get("IPTV_M3U_URL", ""), epg_url="",
            xtream_base=(row.get("XTREAM_BASE_URL") or "").rstrip("/"), xtream_user=row.get("XTREAM_USERNAME", ""),
            xtream_pass=row.get("XTREAM_PASSWORD", ""))
        self.provider = providers.make_provider(self.settings)
        self.by_sid: dict[str, tuple] = {}          # native stream id -> (norm name, url)
        self.by_epg: dict[str, list[str]] = {}
        self.by_name: dict[str, list[str]] = {}
        self.updated = 0.0
        self.error = ""
        self.lock = asyncio.Lock()

    @property
    def kind(self) -> str:
        return self.settings.provider_type

    def summary(self) -> dict:
        return {"label": self.label, "type": self.kind, "channels": len(self.by_sid), "updated": int(self.updated), "error": self.error}

    async def refresh(self, http: httpx.AsyncClient) -> None:
        async with self.lock:
            try:
                rows = await (self._xtream(http) if self.kind == "xtream" else self._m3u(http))
            except providers.ProviderError as e:
                self.error = str(e)
                log.warning("backup %s: %s", self.label, self.error)
                return
            by_sid, by_epg, by_name = {}, {}, {}
            for sid, name, epg, url in rows:
                n = norm_name(name)
                by_sid[sid] = (n, url)
                if epg:
                    by_epg.setdefault(epg.lower(), []).append(sid)
                if n:
                    by_name.setdefault(n, []).append(sid)
            self.by_sid, self.by_epg, self.by_name = by_sid, by_epg, by_name
            self.updated, self.error = time.time(), ""
            log.info("backup %s: %d live channels indexed", self.label, len(by_sid))

    async def _xtream(self, http) -> list[tuple]:
        p = self.provider
        info = await p._get(http, "login")
        ui = (info.get("user_info") or {}) if isinstance(info, dict) else {}
        if str(ui.get("auth", "1")) == "0":
            raise providers.ProviderError("the backup provider refused the login")
        raw = await p._get_raw(http, "live streams", action="get_live_streams")

        def parse():
            out = []
            for c in iter_json_array(raw):
                if isinstance(c, dict) and c.get("stream_id") not in (None, ""):
                    sid = str(c["stream_id"])
                    out.append((sid, str(c.get("name") or ""), str(c.get("epg_channel_id") or ""), p.stream_url("live", sid, "ts")))
            return out
        return await asyncio.to_thread(parse)

    async def _m3u(self, http) -> list[tuple]:
        data = await self.provider.fetch(http)
        return [(i.get("native") or i["id"], i["name"], i.get("epg", ""), i["url"]) for i in data.get("live", [])]

    def match(self, item: dict) -> str | None:
        """The url of this live channel on the backup, or None."""
        if not self.by_sid or item.get("kind") != "live":
            return None
        n = norm_name(item.get("name", ""))
        hit = self.by_sid.get(str(item.get("native") or ""))
        if hit and hit[0] == n:
            return hit[1]
        epg = (item.get("epg") or "").lower()
        if epg and len(self.by_epg.get(epg, ())) == 1:
            return self.by_sid[self.by_epg[epg][0]][1]
        same = self.by_name.get(n, [])
        if len(same) == 1:
            return self.by_sid[same[0]][1]
        return None


class Backups:
    """The configured backups, and which channels lately failed on the main provider (played from a
    backup first for a while, so a retry doesn't wait on the broken stream again)."""
    PREFER_FOR = 15 * 60

    def __init__(self, base: Settings):
        self.base = base
        self.items: list[Backup] = []
        self.failed: dict[str, float] = {}
        self.reload(base)

    def reload(self, base: Settings) -> None:
        self.base = base
        self.items = [Backup(base, r, i) for i, r in enumerate(load(base.state_dir))]

    def __bool__(self) -> bool:
        return bool(self.items)

    async def refresh(self, http) -> None:
        for b in self.items:
            await b.refresh(http)

    def find(self, item: dict) -> tuple[Backup, str] | None:
        for b in self.items:
            url = b.match(item)
            if url:
                return b, url
        return None

    def main_failed(self, iid: str) -> None:
        self.failed[iid] = time.time()
        if len(self.failed) > 500:
            for k in sorted(self.failed, key=self.failed.get)[:250]:
                del self.failed[k]

    def prefer_backup(self, iid: str) -> bool:
        return time.time() - self.failed.get(iid, 0) < self.PREFER_FOR

    def summary(self) -> list[dict]:
        return [b.summary() for b in self.items]
