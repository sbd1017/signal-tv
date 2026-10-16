"""Live scores for the Sports view's live cards, from ESPN's public scoreboards (the same source the
artwork already uses for some crests). Asked only while a page shows live matches; each league's board
is fetched at most every 40 s however many devices ask, and a finished board is kept longer.

/api/scores?q=<comp>|<side a>|<side b>|<start>,... -> {"items": {"<that item>": {"score": {<side>: "2", ...},
"clock": "67'", "state": "in" | "pre" | "post", "detail": "Half Time"}}}, or {"replay": true, "played": <kick-off>}.
A side is a team id ("team:lyon") or, for a club the dataset doesn't know, "name:<the guide's name>"; comp may
be "comp:none". Where to look: the competition's own board, then ESPN's board of every football match that day.
Teams by id are matched with the app's own dataset (tvapp/sports.py); names by their words ("Machida" is
"Machida Zelvia"); both sides must be the same game.
Spoilers: the page never asks for a replay; and an airing that starts long after the real kick-off (over
100 minutes for football) is answered "replay", not with the score.
"""
from __future__ import annotations

import asyncio
import logging
import re
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
ALL_FOOTBALL = "soccer/all"                                         # every football match ESPN has that day
# an airing starting this long after kick-off can't be the live game (the game is over or nearly)
REPLAY_AFTER = {sports.FOOTBALL: 100 * 60, sports.BASKETBALL: 150 * 60, sports.NFL: 200 * 60}

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
# ESPN's league ids (the "l:" in an event's uid) -> our competitions, for a game found on a board of many leagues
LEAGUES = {
    700: "comp:premier-league", 3914: "comp:efl-championship", 3915: "comp:efl-league-one", 3916: "comp:efl-league-two",
    3918: "comp:fa-cup", 3920: "comp:efl-cup", 8097: "comp:womens-super-league", 735: "comp:scottish-premiership",
    740: "comp:laliga", 3921: "comp:laliga-hypermotion", 3951: "comp:copa-del-rey", 730: "comp:serie-a",
    3956: "comp:coppa-italia", 720: "comp:bundesliga", 3927: "comp:2-bundesliga", 3954: "comp:dfb-pokal",
    710: "comp:ligue-1", 3926: "comp:ligue-2", 3952: "comp:coupe-de-france", 725: "comp:eredivisie",
    715: "comp:primeira-liga", 3946: "comp:super-lig", 3901: "comp:jupiler-pro-league", 3960: "comp:eliteserien",
    3945: "comp:allsvenskan", 21231: "comp:saudi-pro-league", 3906: "comp:a-league", 770: "comp:major-league-soccer",
    760: "comp:liga-mx", 630: "comp:brasileirao", 775: "comp:uefa-champions-league", 776: "comp:uefa-europa-league",
    20296: "comp:uefa-conference-league", 19483: "comp:uefa-womens-champions-league", 2395: "comp:uefa-nations-league",
    781: "comp:uefa-euro", 606: "comp:fifa-world-cup", 5501: "comp:fifa-club-world-cup", 783: "comp:copa-libertadores",
    5454: "comp:copa-sudamericana", 3902: "comp:afc-champions-league", 2391: "comp:caf-champions-league",
    786: "comp:world-cup-qualifiers", 787: "comp:world-cup-qualifiers", 788: "comp:world-cup-qualifiers",
    789: "comp:world-cup-qualifiers", 790: "comp:world-cup-qualifiers", 46: "comp:nba", 59: "comp:wnba", 28: "comp:nfl",
}
_LEAGUE = re.compile(r"~l:(\d+)~")


def team_key(team: dict, sport: int) -> str:
    """ESPN's team -> our team id, by its names (full, short, place)."""
    for name in (team.get("displayName"), team.get("shortDisplayName"), team.get("location"), team.get("name")):
        if name:
            i, key, _ = sports.resolve_side(name, sport)
            if i >= 0:
                return key
    return ""


def words(name: str) -> frozenset:
    return frozenset(w for w in sports.norm(name).split() if w not in sports.GENERIC and len(w) > 1)


def parse_board(data: dict, sport: int) -> list[dict]:
    """A scoreboard -> [{"ids": {team id: score}, "names": [(name words, score)] x2, "clock", "state", "detail", "start",
    "comp": our competition id or ""}]."""
    out = []
    for ev in (data or {}).get("events") or []:
        try:
            comp = ev["competitions"][0]
            ids, names = {}, []
            for c in comp["competitors"]:
                team = c.get("team") or {}
                score = str(c.get("score") if c.get("score") not in (None, "") else "")
                k = team_key(team, sport)
                if k:
                    ids[k] = score
                variants = [words(team.get(f) or "") for f in ("displayName", "shortDisplayName", "location", "name")]
                names.append(([v for v in variants if v], score))
            st = ev.get("status") or {}
            typ = st.get("type") or {}
            start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).timestamp()
            league = _LEAGUE.search(f"{ev.get('uid') or ''}~")
            out.append({"ids": ids if len(ids) == 2 else {}, "names": names, "clock": st.get("displayClock") or "",
                        "state": typ.get("state") or "", "detail": typ.get("shortDetail") or typ.get("detail") or "", "start": int(start),
                        "comp": LEAGUES.get(int(league.group(1)), "") if league else ""})
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


def side_words(side: str) -> list[frozenset]:
    """Our side's names as word sets: a known team's every name, or the guide's own name."""
    if side.startswith("team:"):
        ent = sports.BY_ID_KEY.get(side)
        return [w for w in (words(n) for n in ([ent.name, *ent.names] if ent else [])) if w]
    w = words(side[5:])
    return [w] if w else []


def names_fit(ours: list[frozenset], theirs: list[frozenset]) -> bool:
    """Same team by name: one name's words all in the other's ("machida" / "machida zelvia"), a real word among them."""
    return any((a <= b or b <= a) and any(len(x) >= 4 for x in (a & b)) for a in ours for b in theirs)


def find(board: list[dict], a: str, b: str) -> tuple[dict, dict] | None:
    """The game of these two sides on a board -> (game, {a: score, b: score})."""
    if a.startswith("team:") and b.startswith("team:"):
        for g in board:
            if set(g["ids"]) == {a, b}:
                return g, {a: g["ids"][a], b: g["ids"][b]}
    wa, wb = side_words(a), side_words(b)
    if not wa or not wb:
        return None
    hits = []
    for g in board:
        if len(g["names"]) != 2:
            continue
        (n1, s1), (n2, s2) = g["names"]
        if names_fit(wa, n1) and names_fit(wb, n2):
            hits.append((g, {a: s1, b: s2}))
        elif names_fit(wa, n2) and names_fit(wb, n1):
            hits.append((g, {a: s2, b: s1}))
    return hits[0] if len(hits) == 1 else None


class Scores:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.boards: dict[tuple[str, str], tuple[float, list]] = {}          # (path, day) -> (fetched, parsed)
        self.lock = asyncio.Lock()

    async def board(self, path: str, day: str) -> list:
        hit = self.boards.get((path, day))
        now = time.time()
        if hit:
            live = any(v["state"] == "in" or (v["state"] == "pre" and v["start"] - now < 3600) for v in hit[1])
            if now - hit[0] < (LIVE_TTL if live else DONE_TTL):
                return hit[1]
        async with self.lock:                                   # one fetch per board, even with several pages asking
            hit = self.boards.get((path, day))
            if hit and time.time() - hit[0] < LIVE_TTL:
                return hit[1]
            try:
                params = {"dates": day, **({"limit": "1000"} if path == ALL_FOOTBALL else {})}
                r = await self.client.get(f"{ESPN}/{path}/scoreboard", params=params, headers=UA, timeout=15)
                parsed = parse_board(r.json() if r.status_code == 200 else {}, SPORT_OF.get(path.split("/")[0], 0))
            except (httpx.HTTPError, ValueError) as e:
                log.info("scores: %s %s: %s", path, day, e.__class__.__name__)
                parsed = hit[1] if hit else []
            self.boards[(path, day)] = (time.time(), parsed)
            if len(self.boards) > 200:
                for k in sorted(self.boards, key=lambda k: self.boards[k][0])[:100]:
                    del self.boards[k]
            return parsed

    async def ask(self, items: list[tuple[str, str, str, int]]) -> dict:
        """items: (comp, side a, side b, airing start). Only games ESPN lists that day (ET, as its boards are)."""
        out = {}
        for comp, a, b, start in items[:40]:
            paths = SCOREBOARDS.get(comp) or ()
            paths = (paths,) if isinstance(paths, str) else tuple(paths)
            sport = SPORT_OF.get(paths[0].split("/")[0], sports.FOOTBALL) if paths else sports.FOOTBALL
            if sport == sports.FOOTBALL:
                paths += (ALL_FOOTBALL,)                         # the backup: every football game ESPN has that day
            day = datetime.fromtimestamp(start, timezone.utc).astimezone(ET).strftime("%Y%m%d")
            for path in paths:
                got = find(await self.board(path, day), a, b)
                # this meeting: kick-off up to 4 h after the airing starts, or any time in the day before it
                if not got or not -4 * 3600 < start - got[0]["start"] < 24 * 3600:
                    continue
                game, score = got
                key = f"{comp}|{a}|{b}|{start}"
                if start - game["start"] > REPLAY_AFTER.get(sport, 150 * 60):
                    out[key] = {"replay": True, "played": game["start"]}     # aired after the game: never its score
                else:
                    out[key] = {"score": score, "clock": game["clock"], "state": game["state"], "detail": game["detail"]}
                break
        return out
