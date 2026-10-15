"""Live scores for the Sports view's live cards, from ESPN's public scoreboards (the same source the
artwork already uses for some crests). Asked only while a page shows live matches; each league's board
is fetched at most every 40 s however many devices ask, and a finished board is kept longer.

/api/scores?q=<comp>|<team a>|<team b>|<start>,... -> {"items": {"<that item>": {"score": {<team>: "2", ...},
"clock": "67'", "state": "in" | "pre" | "post", "detail": "Half Time"}}}. Teams are matched by name with the
app's own dataset (tvapp/sports.py), so a score is only given when both sides are the same two clubs.
Replays never ask (the page doesn't), so a score can't spoil one.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from tvapp import sports

log = logging.getLogger("tvnext")
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
UA = {"User-Agent": "tv-scores/1 (personal, non-commercial)"}       # ESPN's firewall refuses agents that carry a URL
ET = ZoneInfo("America/New_York")                                     # ESPN's scoreboard days
LIVE_TTL, DONE_TTL = 40, 600

# competition -> ESPN scoreboard(s). Only competitions ESPN covers; anything else simply has no score.
SCOREBOARDS = {
    "comp:premier-league": "soccer/eng.1", "comp:efl-championship": "soccer/eng.2", "comp:efl-league-one": "soccer/eng.3",
    "comp:efl-league-two": "soccer/eng.4", "comp:fa-cup": "soccer/eng.fa", "comp:efl-cup": "soccer/eng.league_cup",
    "comp:womens-super-league": "soccer/eng.w.1", "comp:scottish-premiership": "soccer/sco.1",
    "comp:laliga": "soccer/esp.1", "comp:laliga-hypermotion": "soccer/esp.2", "comp:copa-del-rey": "soccer/esp.copa_del_rey",
    "comp:serie-a": "soccer/ita.1", "comp:coppa-italia": "soccer/ita.coppa_italia",
    "comp:bundesliga": "soccer/ger.1", "comp:2-bundesliga": "soccer/ger.2", "comp:dfb-pokal": "soccer/ger.dfb_pokal",
    "comp:ligue-1": "soccer/fra.1", "comp:ligue-2": "soccer/fra.2", "comp:coupe-de-france": "soccer/fra.coupe_de_france",
    "comp:eredivisie": "soccer/ned.1", "comp:primeira-liga": "soccer/por.1", "comp:liga-portugal-2": "soccer/por.2",
    "comp:super-lig": "soccer/tur.1", "comp:jupiler-pro-league": "soccer/bel.1", "comp:eliteserien": "soccer/nor.1",
    "comp:allsvenskan": "soccer/swe.1", "comp:saudi-pro-league": "soccer/ksa.1", "comp:qatar-stars-league": "soccer/qat.1",
    "comp:uae-pro-league": "soccer/uae.1", "comp:a-league": "soccer/aus.1", "comp:major-league-soccer": "soccer/usa.1",
    "comp:liga-mx": "soccer/mex.1", "comp:brasileirao": "soccer/bra.1",
    "comp:uefa-champions-league": "soccer/uefa.champions", "comp:uefa-europa-league": "soccer/uefa.europa",
    "comp:uefa-conference-league": "soccer/uefa.europa.conf", "comp:uefa-womens-champions-league": "soccer/uefa.wchampions",
    "comp:uefa-nations-league": "soccer/uefa.nations", "comp:uefa-euro": "soccer/uefa.euro", "comp:fifa-world-cup": "soccer/fifa.world",
    "comp:fifa-club-world-cup": "soccer/fifa.cwc", "comp:copa-libertadores": "soccer/conmebol.libertadores",
    "comp:copa-sudamericana": "soccer/conmebol.sudamericana", "comp:afc-champions-league": "soccer/afc.champions",
    "comp:caf-champions-league": "soccer/caf.champions",
    "comp:world-cup-qualifiers": ("soccer/fifa.worldq.uefa", "soccer/fifa.worldq.conmebol", "soccer/fifa.worldq.afc",
                                  "soccer/fifa.worldq.caf", "soccer/fifa.worldq.concacaf"),
    "comp:nba": "basketball/nba", "comp:wnba": "basketball/wnba", "comp:nfl": "football/nfl",
}
SPORT_OF = {"soccer": sports.FOOTBALL, "basketball": sports.BASKETBALL, "football": sports.NFL}


def team_key(team: dict, sport: int) -> str:
    """ESPN's team -> our team id, by its names (full, short, place)."""
    for name in (team.get("displayName"), team.get("shortDisplayName"), team.get("location"), team.get("name")):
        if name:
            i, key, _ = sports.resolve_side(name, sport)
            if i >= 0:
                return key
    return ""


def parse_board(data: dict, sport: int) -> dict[frozenset, dict]:
    """A scoreboard -> {frozenset({team a, team b}): {"score": {team: str}, "clock", "state", "detail", "start"}}."""
    out = {}
    for ev in (data or {}).get("events") or []:
        try:
            comp = ev["competitions"][0]
            sides = {}
            for c in comp["competitors"]:
                k = team_key(c.get("team") or {}, sport)
                if not k:
                    break
                sides[k] = str(c.get("score") if c.get("score") not in (None, "") else "")
            if len(sides) != 2:
                continue
            st = ev.get("status") or {}
            typ = st.get("type") or {}
            start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).timestamp()
            out[frozenset(sides)] = {"score": sides, "clock": st.get("displayClock") or "", "state": typ.get("state") or "",
                                     "detail": typ.get("shortDetail") or typ.get("detail") or "", "start": int(start)}
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


class Scores:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.boards: dict[tuple[str, str], tuple[float, dict]] = {}          # (path, day) -> (fetched, parsed)
        self.lock = asyncio.Lock()

    async def board(self, path: str, day: str) -> dict:
        hit = self.boards.get((path, day))
        now = time.time()
        if hit:
            live = any(v["state"] == "in" or (v["state"] == "pre" and v["start"] - now < 3600) for v in hit[1].values())
            if now - hit[0] < (LIVE_TTL if live else DONE_TTL):
                return hit[1]
        async with self.lock:                                   # one fetch per board, even with several pages asking
            hit = self.boards.get((path, day))
            if hit and time.time() - hit[0] < LIVE_TTL:
                return hit[1]
            try:
                r = await self.client.get(f"{ESPN}/{path}/scoreboard", params={"dates": day}, headers=UA, timeout=10)
                parsed = parse_board(r.json() if r.status_code == 200 else {}, SPORT_OF.get(path.split("/")[0], 0))
            except (httpx.HTTPError, ValueError) as e:
                log.info("scores: %s %s: %s", path, day, e.__class__.__name__)
                parsed = hit[1] if hit else {}
            self.boards[(path, day)] = (time.time(), parsed)
            if len(self.boards) > 200:
                for k in sorted(self.boards, key=lambda k: self.boards[k][0])[:100]:
                    del self.boards[k]
            return parsed

    async def ask(self, items: list[tuple[str, str, str, int]]) -> dict:
        """items: (comp, team a, team b, start). Only pairs ESPN lists that day (ET, as ESPN's boards are)."""
        out = {}
        for comp, a, b, start in items[:40]:
            paths = SCOREBOARDS.get(comp)
            if not paths:
                continue
            day = datetime.fromtimestamp(start, timezone.utc).astimezone(ET).strftime("%Y%m%d")
            for path in (paths,) if isinstance(paths, str) else paths:
                hit = (await self.board(path, day)).get(frozenset((a, b)))
                if hit and abs(hit["start"] - start) < 4 * 3600:     # this meeting, not another one that day
                    out[f"{comp}|{a}|{b}|{start}"] = {k: hit[k] for k in ("score", "clock", "state", "detail")}
                    break
        return out
