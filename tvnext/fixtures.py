"""Is a match in the guide live, or a replay? Many channels air replays with no marker at all (a
regional sports channel showing Saturday's Premier League game on Thursday afternoon, titled exactly
like the live one). The guide can't tell; the real fixture date can.

For a pair of known teams and the time a channel airs their match, TheSportsDB's event search gives
the kick-off of their latest meeting(s):

- a kick-off from 30 minutes before the airing to 90 minutes after it: the airing is the match, live;
- only kick-offs well before it (2.5 h or more, within the last 14 days): a replay, played then;
- anything else (no record, a fixture further away): no verdict, the guide's own reading stands.

Lookups share the artwork worker's TheSportsDB connection and its rate limit (the free key allows
~30 calls a minute). Pages never wait: /api/fixtures answers from the cache and queues the rest.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tvapp import sports


log = logging.getLogger("tvnext")
TTL = 6 * 3600                 # a pair's fixtures are asked again after this (postponements, new rounds)
MISS_TTL = 24 * 3600           # a pair TheSportsDB doesn't know is asked again the next day
LIVE_BEFORE, LIVE_AFTER = 30 * 60, 90 * 60
REPLAY_GAP, REPLAY_WINDOW = int(2.5 * 3600), 14 * 86400


def verdict(kickoffs: list[int], start: int) -> dict | None:
    if any(start - LIVE_BEFORE <= k <= start + LIVE_AFTER for k in kickoffs):
        return {"live": True}
    past = [k for k in kickoffs if start - REPLAY_WINDOW <= k <= start - REPLAY_GAP]
    if past and not any(start - REPLAY_GAP < k < start + LIVE_AFTER for k in kickoffs):
        return {"replay": True, "played": max(past)}
    return None


class Fixtures:
    def __init__(self, lib, src, path: Path):
        self.lib, self.src, self.path = lib, src, path        # src: the Acquirer's TheSportsDB
        self.cache: dict[str, dict] = {}                       # "team:a|team:b" -> {"t": checked, "k": [kick-offs]}
        self.q: asyncio.Queue[str] = asyncio.Queue()
        self.queued: set[str] = set()
        self.dirty = False
        try:
            self.cache = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            pass

    def name(self, key: str) -> str:
        """The team as TheSportsDB spells it: its own record when the crest came from there."""
        meta = self.lib.meta(key) or {}
        if meta.get("source") == "thesportsdb" and meta.get("source_name"):
            return meta["source_name"]
        ent = sports.BY_ID_KEY.get(key)
        return ent.name if ent else ""

    @staticmethod
    def pair(a: str, b: str) -> str:
        return "|".join(sorted((a, b)))

    def fresh(self, p: str) -> dict | None:
        c = self.cache.get(p)
        if c and time.time() - c["t"] < (TTL if c["k"] else MISS_TTL):
            return c
        return None

    def ask(self, items: list[tuple[str, str, int]]) -> tuple[dict, int]:
        """{"a|b|start": verdict} for what is known; the rest is queued. items: (home, away, start)."""
        out = {}
        for a, b, start in items:
            p = self.pair(a, b)
            c = self.fresh(p)
            if c:
                v = verdict(c["k"], start)
                if v:
                    out[f"{a}|{b}|{start}"] = v
            elif p not in self.queued and self.name(a) and self.name(b):
                self.queued.add(p)
                self.q.put_nowait(p)
        return out, self.q.qsize()

    async def kickoffs(self, a: str, b: str) -> list[int]:
        found: set[int] = set()
        for home, away in ((a, b), (b, a)):
            q = f"{self.name(home)} vs {self.name(away)}".replace(" ", "_")
            data = await self.src.api(f"searchevents.php?{httpx.QueryParams({'e': q})}")
            for ev in (data or {}).get("event") or []:
                if (ev.get("strSport") or "Soccer") not in ("Soccer", "Basketball", "American Football"):
                    continue
                ts = ev.get("strTimestamp") or ""
                try:
                    found.add(int(datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()))
                except ValueError:
                    pass
        return sorted(found)

    async def run(self):
        while True:
            p = await self.q.get()
            try:
                a, b = p.split("|")
                self.cache[p] = {"t": time.time(), "k": await self.kickoffs(a, b)}
                self.dirty = True
            except (httpx.HTTPError, ValueError) as e:
                self.cache[p] = {"t": time.time() - TTL + 1800, "k": []}     # a failed lookup: try again in 30 min
                log.info("fixtures: %s: %s", p, e.__class__.__name__)
            finally:
                self.queued.discard(p)
                if self.q.empty():
                    self.flush()

    def flush(self):
        if not self.dirty:
            return
        cutoff = time.time() - 7 * 86400
        self.cache = {k: v for k, v in self.cache.items() if v["t"] > cutoff}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, separators=(",", ":")))
        tmp.replace(self.path)
        self.dirty = False
