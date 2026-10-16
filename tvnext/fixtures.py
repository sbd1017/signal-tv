"""Is a match in the guide live, or a replay? Many channels air replays with no marker at all (a
regional sports channel showing Saturday's Premier League game on Thursday afternoon, titled exactly
like the live one). The guide can't tell; the real fixture date can.

For a pair of known teams and the time a channel airs their match, ESPN's daily scoreboards (every
football game it lists that day; the NBA's and the NFL's) give the kick-off of their meetings around it:

- a kick-off from 30 minutes before the airing to 90 minutes after it: the airing is the match, live;
- only kick-offs well before it (2.5 h or more, within the last 14 days): a replay, played then;
- anything else (no record, a fixture further away): no verdict, the guide's own reading stands.

The meeting's competition comes with it, for a listing whose guide never says ("UNION SG - REAL
SOCIEDAD"): the page shows it only when the guide named none. TheSportsDB's event search is the fallback
for pairs ESPN doesn't list (its free API is often down). Pages never wait: /api/fixtures answers from the
cache and queues the rest. A day's board is fetched once an hour (older days twice a day) however many
pairs need it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from tvapp import sports

from . import scores

log = logging.getLogger("tvnext")
TTL = 6 * 3600                 # a pair's fixtures are asked again after this (postponements, new rounds)
MISS_TTL = 24 * 3600           # a pair nobody lists is asked again the next day
LIVE_BEFORE, LIVE_AFTER = 30 * 60, 90 * 60
REPLAY_GAP, REPLAY_WINDOW = int(2.5 * 3600), 14 * 86400
# an airing that starts this long after the real kick-off is past the game (football: over 100 minutes)
GAPS = {sports.FOOTBALL: 100 * 60, sports.BASKETBALL: 150 * 60, sports.NFL: 200 * 60}
BOARDS = {sports.FOOTBALL: scores.ALL_FOOTBALL, sports.BASKETBALL: "basketball/nba", sports.NFL: "football/nfl"}
DAY_TTL, OLD_DAY_TTL = 3600, 12 * 3600


def meeting(kickoffs: list[int], start: int, gap: int = REPLAY_GAP) -> tuple[dict, int] | None:
    """(verdict, the kick-off it rests on) or None."""
    live = [k for k in kickoffs if start - LIVE_BEFORE <= k <= start + LIVE_AFTER]
    if live:
        return {"live": True}, live[0]
    past = [k for k in kickoffs if start - REPLAY_WINDOW <= k <= start - gap]
    if past and not any(start - gap < k < start + LIVE_AFTER for k in kickoffs):
        return {"replay": True, "played": max(past)}, max(past)
    return None


def verdict(kickoffs: list[int], start: int, gap: int = REPLAY_GAP) -> dict | None:
    m = meeting(kickoffs, start, gap)
    return m[0] if m else None


def days(start: int) -> list[str]:
    """ESPN's scoreboard days (US Eastern) from the replay window's start to the day after the airing."""
    first = datetime.fromtimestamp(start - REPLAY_WINDOW, timezone.utc).astimezone(scores.ET).date()
    last = datetime.fromtimestamp(start + 86400, timezone.utc).astimezone(scores.ET).date()
    return [(first + timedelta(d)).strftime("%Y%m%d") for d in range((last - first).days + 1)]


class Fixtures:
    def __init__(self, lib, src, path: Path, client: httpx.AsyncClient | None = None):
        self.lib, self.src, self.path = lib, src, path        # src: the Acquirer's TheSportsDB
        self.client = client                                   # ESPN's scoreboards; None: TheSportsDB only
        # "team:a|team:b" -> {"t": checked, "k": [kick-offs], "c": {kick-off: competition}, "w": [from, to] covered}
        self.cache: dict[str, dict] = {}
        self.boards: dict[tuple[str, str], tuple[float, list]] = {}
        self.q: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
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

    def fresh(self, p: str, start: int) -> dict | None:
        c = self.cache.get(p)
        w = (c or {}).get("w") or (0, 0)
        # the days looked at must cover this airing's window (a day's slack at the far end)
        if c and time.time() - c["t"] < (TTL if c["k"] else MISS_TTL) and w[0] <= start - REPLAY_WINDOW + 86400 \
                and start + LIVE_AFTER <= w[1]:
            return c
        return None

    def ask(self, items: list[tuple[str, str, int]]) -> tuple[dict, int]:
        """{"a|b|start": verdict} for what is known; the rest is queued. items: (home, away, start).
        A verdict may carry the meeting's competition: "comp" (id) and "comp_name"."""
        out = {}
        for a, b, start in items:
            p = self.pair(a, b)
            c = self.fresh(p, start)
            if c:
                ent = sports.BY_ID_KEY.get(a)
                m = meeting(c["k"], start, GAPS.get(ent.sport if ent else 0, REPLAY_GAP))
                if m:
                    v, kick = m
                    comp = (c.get("c") or {}).get(str(kick), "")
                    if comp in sports.BY_ID_KEY:
                        v = {**v, "comp": comp, "comp_name": sports.BY_ID_KEY[comp].name}
                    out[f"{a}|{b}|{start}"] = v
            elif p not in self.queued and self.name(a) and self.name(b):
                self.queued.add(p)
                self.q.put_nowait((p, start))
        return out, self.q.qsize()

    async def board(self, path: str, day: str) -> list:
        hit = self.boards.get((path, day))
        ttl = OLD_DAY_TTL if day < datetime.now(scores.ET).strftime("%Y%m%d") else DAY_TTL
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        try:
            params = {"dates": day, **({"limit": "1000"} if path == scores.ALL_FOOTBALL else {})}
            r = await self.client.get(f"{scores.ESPN}/{path}/scoreboard", params=params, headers=scores.UA, timeout=20)
            if r.status_code != 200:
                raise ValueError(r.status_code)
            parsed = await asyncio.to_thread(scores.parse_board, r.json(), scores.SPORT_OF[path.split("/")[0]])
        except (httpx.HTTPError, ValueError) as e:
            log.info("fixtures: %s %s: %s", path, day, e.__class__.__name__)
            parsed = hit[1] if hit else []
            self.boards[(path, day)] = (time.time() - ttl + 300, parsed)       # ESPN unreachable: again in 5 min
            return parsed
        self.boards[(path, day)] = (time.time(), parsed)
        if len(self.boards) > 60:
            for k in sorted(self.boards, key=lambda k: self.boards[k][0])[:20]:
                del self.boards[k]
        return parsed

    async def espn(self, a: str, b: str, start: int) -> dict[int, str]:
        """Kick-off -> competition of every meeting of a and b ESPN lists around this airing."""
        ent = sports.BY_ID_KEY.get(a)
        path = BOARDS.get(ent.sport if ent else 0)
        if not path or not self.client:
            return {}
        found = {}
        for board in await asyncio.gather(*(self.board(path, day) for day in days(start))):
            got = scores.find(board, a, b)
            if got:
                found[got[0]["start"]] = got[0]["comp"]
        return found

    async def tsdb(self, a: str, b: str) -> list[int]:
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

    async def lookup(self, a: str, b: str, start: int) -> dict:
        met = await self.espn(a, b, start)
        kicks = sorted(met)
        if not kicks and self.src:
            try:
                kicks = await self.tsdb(a, b)
            except (httpx.HTTPError, ValueError) as e:
                log.info("fixtures: TheSportsDB %s|%s: %s", a, b, e.__class__.__name__)
        return {"t": time.time(), "k": kicks, "c": {str(k): c for k, c in met.items() if c},
                "w": [start - REPLAY_WINDOW, start + 86400]}

    async def run(self):
        while True:
            p, start = await self.q.get()
            try:
                a, b = p.split("|")
                self.cache[p] = await self.lookup(a, b, start)
                self.dirty = True
            except (httpx.HTTPError, ValueError) as e:
                self.cache[p] = {"t": time.time() - MISS_TTL + 1800, "k": [], "w": [start - REPLAY_WINDOW, start + 86400]}
                log.info("fixtures: %s: %s", p, e.__class__.__name__)       # a failed lookup: try again in 30 min
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
