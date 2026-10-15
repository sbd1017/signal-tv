"""Sports artwork library: team crests and competition logos, cache first.

Rendering only ever reads local files. A canonical entity ("team:bayern-munich",
"comp:premier-league" - tvapp/sports.py ids, never a guide's spelling) without artwork is queued
for a background lookup; the queue runs one request at a time per source (TheSportsDB's free API:
~27/min), so a 400-event Sports day never fans out into hundreds of lookups.

Sources, in order (TVN_ART_SOURCES), each asked only when the ones before had no confident answer:
  thesportsdb  community database, free key: name search for teams, a verified league id per competition
  espn         ESPN's public site API: the teams listed in the club's own country's leagues (or in a
               continental competition, then confirmed by the team's home league), national teams in
               international competitions, a verified league slug per competition
  wikidata     the entity's Wikidata item (clubs: exact label/alias + "association football club" +
               country; competitions: an explicit item id, label-checked) and its logo (P154) from
               Wikimedia Commons, with the file's own licence and author recorded

Accuracy over coverage. A crest is only attached when the source's team has one of the entity's
own names (sports.py) as its name or listed alternate, the right sport, men's team, and - for
clubs - the expected country; national teams must be the country's own team in an international
competition. Anything ambiguous stays a miss and the page keeps its generated crest. Manual
mappings (overrides.json) pin one source record; each carries a note saying how it was checked.

Layout under STATE/sports-art/ (durable; the generated derivatives can be rebuilt):
  teams/<slug>/original.<ext> + meta.json       competitions/<slug>/...
  derivatives/<teams|competitions>/<slug>/<64|128|256>.webp
  stadiums/ fanart/                             (reserved: photos are not used yet)
  overrides.json   manual corrections, on top of tvnext/overrides.json (shipped, in git):
                   {"source": "thesportsdb", "id": "133604"} | {"source": "espn", "league": "soccer/ksa.1", "id": "2276"}
                   | {"source": "wikidata", "qid": "Q617077"} | {"none": true}
  misses.json      entities looked up without a confident match (retried after ART_MISS_RETRY_DAYS)
  gaps.json        artwork-gap registry: what the page actually drew with a generated crest/mark, and why
  log.jsonl        one line per acquisition attempt
"""
from __future__ import annotations

import asyncio
import collections
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

from tvapp import sports

from . import config

SIZES = (64, 128, 256)
SOURCE = "thesportsdb"
LICENCE = ("TheSportsDB community artwork (www.thesportsdb.com), used for personal, non-commercial display; "
           "crests and logos are trademarks of their clubs and competitions.")
ESPN_LICENCE = ("ESPN public site API (site.api.espn.com; unofficial, no key), used for personal, non-commercial display; "
                "crests and logos are trademarks of their clubs and competitions.")
TRADEMARK = "the crest or logo itself is a trademark of its club or competition"
UA = {"User-Agent": f"signal-tv-art/1 (personal, non-commercial; {config.ART_CONTACT})"}   # Wikimedia asks for a contact
TSDB_SPORT = {"football": "Soccer", "basketball": "Basketball", "nfl": "American Football", "cricket": "Cricket",
              "rugby": "Rugby", "tennis": "Tennis", "f1": "Motorsport", "mma": "Fighting"}

# Expected country of each club (TheSportsDB strCountry spelling; synonyms below). Part of the match,
# not a correction: a same-named club elsewhere (Inter Miami / Inter Milan, Rangers in Scotland /
# Chile, Sabah in Azerbaijan / Malaysia) is refused.
_COUNTRIES = {
    "England": "arsenal aston-villa afc-bournemouth brentford brighton-hove-albion burnley chelsea crystal-palace everton fulham "
               "leeds-united liverpool manchester-city manchester-united newcastle-united nottingham-forest sunderland "
               "tottenham-hotspur west-ham-united wolverhampton-wanderers leicester-city southampton ipswich-town sheffield-united "
               "sheffield-wednesday west-bromwich-albion middlesbrough norwich-city coventry-city watford stoke-city hull-city "
               "derby-county queens-park-rangers birmingham-city portsmouth lincoln-city",
    "Wales": "wrexham",
    "Scotland": "celtic rangers aberdeen heart-of-midlothian motherwell",
    "Spain": "real-madrid barcelona atletico-madrid athletic-club real-sociedad real-betis sevilla valencia-cf villarreal celta-vigo "
             "girona osasuna getafe rayo-vallecano mallorca espanyol elche deportivo-la-coruna malaga levante alaves baskonia valencia-basket manresa",
    "Italy": "juventus inter-milan ac-milan napoli as-roma lazio atalanta fiorentina bologna torino como venezia udinese cagliari "
             "genoa sassuolo parma lecce monza frosinone sudtirol virtus-bologna olimpia-milano derthona",
    "Germany": "bayern-munich borussia-dortmund bayer-leverkusen rb-leipzig eintracht-frankfurt vfb-stuttgart "
               "borussia-monchengladbach vfl-wolfsburg sc-freiburg werder-bremen union-berlin hamburger-sv tsg-hoffenheim "
               "fc-augsburg schalke-04 1-fc-nurnberg hansa-rostock 1-fc-saarbrucken msv-duisburg fortuna-koln rot-weiss-essen sv-meppen 1-fc-koln holstein-kiel hertha-bsc preussen-munster fortuna-dusseldorf",
    "France": "paris-saint-germain marseille lyon as-monaco lille ogc-nice rc-lens stade-rennais strasbourg auxerre le-mans "
              "stade-brestois angers troyes fc-nantes stade-de-reims saint-etienne rodez paris-basketball asvel",
    "Portugal": "benfica fc-porto sporting-cp sc-braga famalicao alverca maritimo vitoria-guimaraes torreense",
    "Netherlands": "ajax psv-eindhoven feyenoord az-alkmaar nec-nijmegen heerenveen",
    "Turkey": "galatasaray fenerbahce besiktas trabzonspor rizespor anadolu-efes",
    "Belgium": "club-brugge anderlecht union-saint-gilloise",
    "Austria": "red-bull-salzburg lask sturm-graz",
    "Switzerland": "basel servette sion lugano",
    "Czechia": "slavia-prague sparta-prague pardubice jablonec",
    "Slovenia": "nk-celje",
    "Azerbaijan": "sabah neftchi",
    "Norway": "bodo-glimt viking brann",
    "Poland": "lech-poznan legia-warsaw rakow-czestochowa wisla-krakow wisla-plock wieczysta-krakow cracovia gks-katowice "
              "pogon-szczecin korona-kielce radomiak-radom slask-wroclaw piast-gliwice widzew-lodz zaglebie-lubin motor-lublin "
              "jagiellonia-bialystok gornik-zabrze",
    "Ukraine": "shakhtar-donetsk",
    "Croatia": "dinamo-zagreb hajduk-split",
    "Serbia": "red-star-belgrade partizan",
    "Greece": "olympiacos panathinaikos paok ofi-crete kalamata aris-thessaloniki aek-athens",
    "Cyprus": "apoel nea-salamina omonia-nicosia pafos",
    "Saudi Arabia": "al-hilal al-nassr al-ittihad al-ahli-saudi",
    "Qatar": "al-sadd al-gharafa",
    "United Arab Emirates": "shabab-al-ahli al-ain al-wasl al-jazira dubai-basketball",
    "Iraq": "al-shorta air-force-club",
    "Oman": "al-seeb",
    "Jordan": "al-hussein",
    "Thailand": "ratchaburi buriram-united",
    "South Korea": "pohang-steelers fc-seoul gangwon",
    "Malaysia": "johor-darul-tazim",
    "Japan": "gamba-osaka kyoto-sanga kashima-antlers kashiwa-reysol",
    "Australia": "newcastle-jets melbourne-victory adelaide-united",
    "India": "east-bengal",
    "Vietnam": "cong-an-ha-noi",
    "Singapore": "lion-city-sailors tampines-rovers",
    "United States": "inter-miami la-galaxy atlanta-hawks boston-celtics brooklyn-nets charlotte-hornets chicago-bulls cleveland-cavaliers dallas-mavericks denver-nuggets detroit-pistons golden-state-warriors houston-rockets indiana-pacers la-clippers los-angeles-lakers memphis-grizzlies miami-heat milwaukee-bucks minnesota-timberwolves new-orleans-pelicans new-york-knicks oklahoma-city-thunder orlando-magic philadelphia-76ers phoenix-suns portland-trail-blazers sacramento-kings san-antonio-spurs utah-jazz washington-wizards arizona-cardinals atlanta-falcons baltimore-ravens buffalo-bills carolina-panthers chicago-bears cincinnati-bengals cleveland-browns dallas-cowboys denver-broncos detroit-lions green-bay-packers houston-texans indianapolis-colts jacksonville-jaguars kansas-city-chiefs las-vegas-raiders los-angeles-chargers los-angeles-rams miami-dolphins minnesota-vikings new-england-patriots new-orleans-saints new-york-giants new-york-jets philadelphia-eagles pittsburgh-steelers san-francisco-49ers seattle-seahawks tampa-bay-buccaneers tennessee-titans washington-commanders",
    "Brazil": "flamengo palmeiras corinthians vasco-da-gama fluminense",
    "Argentina": "boca-juniors river-plate estudiantes",
    "Mexico": "club-america",
    "Finland": "kups",
    "Lithuania": "kauno-zalgiris zalgiris-kaunas",
    "Romania": "universitatea-craiova dinamo-bucuresti",
    "Bulgaria": "cska-sofia",
    "China": "shanghai-shenhua",
    "Iran": "esteghlal",
    "Israel": "hapoel-beer-sheva maccabi-tel-aviv hapoel-tel-aviv",
    "Denmark": "fc-kobenhavn",
    "Gibraltar": "lincoln-red-imps",
    "Armenia": "ararat-armenia",
    "Montenegro": "buducnost",
    "Canada": "toronto-raptors",
}
CLUB_COUNTRY = {f"team:{slug}": c for c, slugs in _COUNTRIES.items() for slug in slugs.split()}
COUNTRY_SYNONYMS = {"Czechia": {"Czech Republic"}, "South Korea": {"Korea Republic", "Korea, South", "Republic of Korea"},
                    "United Arab Emirates": {"UAE"}, "Turkey": {"Türkiye", "Turkiye"}, "Vietnam": {"Viet Nam"}}
NATIONAL_LEAGUE = re.compile(r"world cup|international|nations|euro|copa america|african cup|asian cup|gold cup|friendl|qualif", re.I)
NOT_FIRST_TEAM = re.compile(r"\b(women|womens|ladies|w|u\d\d|ii|iii|b|reserves?|academy|youth|futsal|beach)\b", re.I)

# Competition -> (TheSportsDB league id, expected country or None). Each one is verified on lookup.
LEAGUES = {
    "comp:premier-league": ("4328", "England"), "comp:efl-championship": ("4329", "England"), "comp:efl-league-one": ("4396", "England"),
    "comp:efl-league-two": ("4397", "England"), "comp:fa-cup": ("4482", "England"), "comp:efl-cup": ("4570", "England"),
    "comp:scottish-premiership": ("4330", "Scotland"), "comp:laliga": ("4335", "Spain"), "comp:laliga-hypermotion": ("4400", "Spain"),
    "comp:copa-del-rey": ("4483", "Spain"), "comp:serie-a": ("4332", "Italy"), "comp:coppa-italia": ("4506", "Italy"),
    "comp:bundesliga": ("4331", "Germany"), "comp:2-bundesliga": ("4399", "Germany"), "comp:dfb-pokal": ("4485", "Germany"),
    "comp:ligue-1": ("4334", "France"), "comp:ligue-2": ("4401", "France"), "comp:coupe-de-france": ("4484", "France"),
    "comp:eredivisie": ("4337", "Netherlands"), "comp:primeira-liga": ("4344", "Portugal"), "comp:super-lig": ("4339", "Turkey"),
    "comp:jupiler-pro-league": ("4338", "Belgium"), "comp:saudi-pro-league": ("4668", "Saudi Arabia"),
    "comp:major-league-soccer": ("4346", "United States"), "comp:liga-mx": ("4350", "Mexico"), "comp:brasileirao": ("4351", "Brazil"),
    "comp:eliteserien": ("4358", "Norway"), "comp:allsvenskan": ("4347", "Sweden"), "comp:ekstraklasa": ("4422", "Poland"),
    "comp:uefa-champions-league": ("4480", None), "comp:uefa-europa-league": ("4481", None), "comp:uefa-conference-league": ("5071", None),
    "comp:uefa-nations-league": ("4490", None), "comp:uefa-euro": ("4502", None), "comp:fifa-world-cup": ("4429", None),
    "comp:fifa-club-world-cup": ("4503", None), "comp:copa-libertadores": ("4501", None), "comp:womens-super-league": ("4849", "England"),
    "comp:nba": ("4387", "United States"), "comp:wnba": ("4516", "United States"), "comp:euroleague": ("4546", None),
    "comp:nfl": ("4391", "United States"), "comp:indian-premier-league": ("4460", "India"), "comp:six-nations": ("4714", None),
    "comp:premiership-rugby": ("4414", "England"), "comp:top-14": ("4430", "France"), "comp:nrl": ("4416", "Australia"),
    "comp:formula-1": ("4370", None), "comp:ufc": ("4443", None),
    # added 2026-10-13 (league ids read from the source, each still name/sport/country-checked on lookup)
    "comp:afc-champions-league": ("4719", None), "comp:copa-sudamericana": ("4724", None), "comp:caf-champions-league": ("4720", None),
    "comp:a-league": ("4356", "Australia"), "comp:qatar-stars-league": ("4663", "Qatar"),
    "comp:uae-pro-league": ("4678", "United Arab Emirates"), "comp:liga-endesa": ("4408", "Spain"), "comp:aba-league": ("4477", None),
    "comp:eurocup": ("4547", None), "comp:atp-tour": ("4464", None), "comp:wta-tour": ("4517", None),
    "comp:united-rugby-championship": ("4446", None), "comp:super-rugby": ("4551", None), "comp:the-rugby-championship": ("4986", None),
    "comp:rugby-world-cup": ("4574", None), "comp:investec-champions-cup": ("4550", None), "comp:bellator": ("4467", None),
}

# ESPN: country -> the league-slug prefixes its clubs play under; competitions with their own slug.
ESPN_PREFIX = {
    "England": ("eng",), "Wales": ("wal", "eng"), "Scotland": ("sco",), "Spain": ("esp",), "Italy": ("ita",), "Germany": ("ger",),
    "France": ("fra",), "Portugal": ("por",), "Netherlands": ("ned",), "Turkey": ("tur",), "Belgium": ("bel",), "Austria": ("aut",),
    "Switzerland": ("sui",), "Czechia": ("cze",), "Slovenia": ("svn",), "Azerbaijan": ("aze",), "Norway": ("nor",), "Poland": ("pol",),
    "Ukraine": ("ukr",), "Croatia": ("cro",), "Serbia": ("srb",), "Greece": ("gre",), "Cyprus": ("cyp",), "Saudi Arabia": ("ksa",),
    "Qatar": ("qat",), "United Arab Emirates": ("uae",), "Iraq": ("irq",), "Oman": ("oma",), "Jordan": ("jor",), "Thailand": ("tha",),
    "South Korea": ("kor",), "Malaysia": ("mys",), "Japan": ("jpn",), "Australia": ("aus",), "India": ("ind",), "Vietnam": ("vie",),
    "Singapore": ("sgp",), "United States": ("usa",), "Brazil": ("bra",), "Argentina": ("arg",), "Mexico": ("mex",),
}
ESPN_CONTINENTAL = ("soccer/uefa.champions", "soccer/uefa.europa", "soccer/uefa.europa.conf", "soccer/afc.champions",
                    "soccer/conmebol.libertadores", "soccer/conmebol.sudamericana")
ESPN_NATIONAL = ("soccer/fifa.world", "soccer/fifa.worldq.uefa", "soccer/uefa.nations", "soccer/fifa.worldq.conmebol",
                 "soccer/fifa.worldq.afc", "soccer/fifa.worldq.caf", "soccer/fifa.worldq.concacaf")
ESPN_LEAGUES = {
    "comp:afc-champions-league": "soccer/afc.champions", "comp:copa-sudamericana": "soccer/conmebol.sudamericana",
    "comp:caf-champions-league": "soccer/caf.champions", "comp:uefa-womens-champions-league": "soccer/uefa.wchampions",
    "comp:a-league": "soccer/aus.1", "comp:liga-portugal-2": "soccer/por.2", "comp:qatar-stars-league": "soccer/qat.1",
    "comp:uae-pro-league": "soccer/uae.1", "comp:pfl": "mma/pfl", "comp:bellator": "mma/bellator",
}

# Wikidata items for competitions (each label-checked on lookup); the logo is the item's P154.
WIKIDATA_COMPS = {
    "comp:uefa-youth-league": "Q617077", "comp:davis-cup": "Q132377", "comp:australian-open": "Q60874",
    "comp:uefa-womens-champions-league": "Q748389", "comp:liga-portugal-2": "Q754488", "comp:pfl": "Q891610",
    "comp:bellator": "Q815817", "comp:copa-sudamericana": "Q60585", "comp:a-league": "Q219586", "comp:rugby-world-cup": "Q16640",
    "comp:united-rugby-championship": "Q6002", "comp:the-rugby-championship": "Q58344", "comp:eurocup": "Q456092",
    "comp:liga-endesa": "Q1126104",
}
WD_FOOTBALL_CLUB = "Q476028"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(eid: str) -> str:
    return eid.split(":", 1)[1]


# ------------------------------------------------------------------ canonical entities
def entities() -> dict[str, dict]:
    """sports.py DATA with original spellings: key -> {kind, section, sport, names, weak, priority}."""
    out: dict[str, dict] = {}
    section, sport = "", ""
    for raw in sports.DATA.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            section, sport = line[1:].split()
            continue
        key, sep, rest = line.partition(" = ")
        if not sep:
            continue
        parts = [p.strip() for p in rest.split(";")]
        names = [n.strip() for n in parts[0].split("|") if n.strip()]
        prio = next((int(p.split(":", 1)[1]) for p in parts[1:] if p.startswith("priority:")), 0)
        weak = next(([n.strip() for n in p.split(":", 1)[1].split("|") if n.strip()] for p in parts[1:] if p.startswith("weak:")), [])
        out[key] = {"key": key, "kind": "comp" if key.startswith("comp:") else "team", "section": section,
                    "sport": "football" if section == "national" else sport, "names": names, "weak": weak, "priority": prio}
    return out


# ------------------------------------------------------------------ matching (pure)
def _alts(text: str | None) -> list[str]:
    return [a.strip() for a in re.split(r"[,;/]", text or "") if a.strip()] if text else []


_FOLD = str.maketrans({"ø": "o", "ł": "l", "ß": "ss", "æ": "ae", "đ": "d", "ı": "i", "œ": "oe"})


def _key(name: str) -> str:
    """Name for comparing across sources: sports.norm, letters NFKD can't split folded ("Bodø" = "Bodo"),
    club-form words dropped ("FC Basel" = "Basel")."""
    words = sports.norm(name).translate(_FOLD).split()
    return " ".join(w for w in words if w not in sports.GENERIC) or " ".join(words)


def _keys(names) -> set[str]:
    return {k for n in names for k in (sports.norm(n).translate(_FOLD), _key(n)) if k}


def _strip_the(n: str) -> str:
    return re.sub(r"^the ", "", n)


def match_team(ent: dict, cands: list[dict]) -> tuple[dict | None, str]:
    """The one TheSportsDB team that is this entity, or (None, why not)."""
    names = {sports.norm(n) for n in ent["names"]}
    want_sport = TSDB_SPORT.get(ent["sport"], "")
    national = ent["section"] == "national"
    country = None if national else CLUB_COUNTRY.get(ent["key"])
    if not national and not country:
        return None, "no expected country for this club"
    ok = []
    why = "no candidates"
    for c in cands or []:
        team = c.get("strTeam") or ""
        cnames = {sports.norm(team), sports.norm(c.get("strTeamShort") or "")} | {sports.norm(a) for a in _alts(c.get("strTeamAlternate"))}
        cnames.discard("")
        if c.get("strSport") != want_sport:
            why = f"sport {c.get('strSport')}"
            continue
        if (c.get("strGender") or "Male") != "Male" or NOT_FIRST_TEAM.search(team):
            why = f"not the men's first team: {team}"
            continue
        if not (names & cnames):
            why = f"name: {team}"
            continue
        if national:
            # the country's own side: its name or country is the entity's, in an international competition
            # (the source spells some countries its own way: "Macedonia" for North Macedonia)
            if not ({sports.norm(team), sports.norm(c.get("strCountry") or "")} & names) or not NATIONAL_LEAGUE.search(c.get("strLeague") or ""):
                why = f"not a national team: {team} ({c.get('strLeague')})"
                continue
        elif not same_country(country, c.get("strCountry")):
            why = f"country {c.get('strCountry')} (expected {country})"
            continue
        ok.append(c)
    ids = {c["idTeam"] for c in ok}
    if len(ids) == 1:
        c = ok[0]
        how = "name" if sports.norm(c["strTeam"]) in names else "alternate name"
        return c, f"{how} + sport + {'national team' if national else 'country'}"
    if len(ids) > 1:
        return None, f"ambiguous: {len(ids)} teams"
    return None, why


HOME_NATIONS = {"England", "Scotland", "Wales", "Northern Ireland"}


def same_country(expected: str, got: str | None) -> bool:
    """"The Netherlands" is the Netherlands, "Czech Republic" is Czechia; an English club or cup may be
    filed under the UK."""
    got = re.sub(r"^the ", "", (got or "").strip(), flags=re.I)
    return got == expected or got in COUNTRY_SYNONYMS.get(expected, ()) or (expected in HOME_NATIONS and got == "United Kingdom")


def names_in(ent: dict, source_names) -> bool:
    """Every word of one of the entity's names appears, in order and as whole words, in one of the
    source's names: the source often prefixes a country ("English Premier League") or adds a sponsor."""
    names = {_strip_the(sports.norm(n)) for n in ent["names"]}
    for ln in {_strip_the(sports.norm(x)) for x in source_names if x}:
        for n in names:
            if n and re.search(rf"(^| ){re.escape(n)}( |$)", ln):
                return True
    return False


def verify_league(ent: dict, league: dict, country: str | None) -> tuple[bool, str]:
    want_sport = TSDB_SPORT.get(ent["sport"], "")
    if league.get("strSport") != want_sport:
        return False, f"sport {league.get('strSport')}"
    if country and not same_country(country, league.get("strCountry")):
        return False, f"country {league.get('strCountry')}"
    if names_in(ent, [league.get("strLeague"), *_alts(league.get("strLeagueAlternate"))]):
        return True, f"name ({league.get('strLeague')}) + sport" + (" + country" if country else "")
    return False, f"name {league.get('strLeague')}"


def match_espn_team(ent: dict, teams: list[dict], national: bool) -> tuple[dict | None, str]:
    """The one ESPN team in a list that carries one of the entity's names. A national team must have
    the country's own name exactly (not a club or a youth side of it)."""
    want = {sports.norm(n) for n in ent["names"]} if national else _keys(ent["names"] + ent.get("weak", []))
    ok = {}
    for t in teams:
        t = t.get("team", t)
        cand = [t.get("displayName"), t.get("shortDisplayName"), t.get("name"), t.get("location")]
        got = {sports.norm(c) for c in cand if c} if national else _keys(c for c in cand if c)
        if want & got and not NOT_FIRST_TEAM.search(t.get("displayName") or ""):
            ok[t["id"]] = t
    if len(ok) == 1:
        return next(iter(ok.values())), "name"
    return None, (f"ambiguous: {len(ok)} teams" if ok else "name not listed")


def espn_logo(logos: list[dict]) -> str:
    """The logo made for dark backgrounds when there is one (this site is dark), else the default."""
    pick = next((lg for lg in logos or [] if "dark" in (lg.get("rel") or [])), None) or next(iter(logos or []), None)
    return (pick or {}).get("href", "")


def wd_claims(item: dict, prop: str) -> list[dict]:
    return [c for c in item.get("claims", {}).get(prop, []) if c.get("rank") != "deprecated"
            and c.get("mainsnak", {}).get("datavalue")]


def wd_logo(item: dict) -> str:
    """The current logo (P154): the preferred one, else one without an end date, the most recent start."""
    cl = wd_claims(item, "P154")
    pref = [c for c in cl if c.get("rank") == "preferred"]
    live = [c for c in cl if "P582" not in c.get("qualifiers", {})]
    pick = pref or live
    if not pick:
        return ""

    def start(c):
        q = c.get("qualifiers", {}).get("P580") or [{}]
        return ((q[0].get("datavalue") or {}).get("value") or {}).get("time", "")
    return max(pick, key=start)["mainsnak"]["datavalue"]["value"]


def wd_names(item: dict) -> list[str]:
    lab = (item.get("labels", {}).get("en") or {}).get("value")
    return [n for n in [lab, *(a.get("value") for a in item.get("aliases", {}).get("en", []))] if n]


def wd_ids(item: dict, prop: str) -> list[str]:
    return [c["mainsnak"]["datavalue"]["value"].get("id") for c in wd_claims(item, prop)]


# ------------------------------------------------------------------ the library on disk
class Library:
    def __init__(self, root: Path | None = None):
        self.root = root or (config.STATE / "sports-art")
        for d in ("teams", "competitions", "stadiums", "fanart", "derivatives/teams", "derivatives/competitions"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self._index: dict | None = None
        self.gaps = Gaps(self.root / "gaps.json")

    def dir(self, eid: str) -> Path:
        return self.root / ("competitions" if eid.startswith("comp:") else "teams") / slug(eid)

    def meta(self, eid: str) -> dict | None:
        try:
            return json.loads((self.dir(eid) / "meta.json").read_text())
        except (OSError, ValueError):
            return None

    def _json(self, name: str) -> dict:
        try:
            return json.loads((self.root / name).read_text())
        except (OSError, ValueError):
            return {}

    def _write_json(self, name: str, data: dict) -> None:
        p = self.root / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
        os.replace(tmp, p)

    def overrides(self) -> dict:
        """Manual corrections: the defaults shipped with the code (tvnext/overrides.json, in git), then
        the Pi's own STATE/sports-art/overrides.json on top."""
        try:
            base = json.loads((Path(__file__).with_name("overrides.json")).read_text())
        except (OSError, ValueError):
            base = {}
        return {**base, **self._json("overrides.json")}

    def misses(self) -> dict:
        return self._json("misses.json")

    def log(self, entry: dict) -> None:
        with open(self.root / "log.jsonl", "a") as f:
            f.write(json.dumps({"t": now_iso(), **entry}, ensure_ascii=False) + "\n")

    def index(self) -> dict:
        """eid -> {v, sizes} for every entity with artwork (cached; rebuilt when something changes)."""
        if self._index is None:
            idx = {}
            for kind in ("teams", "competitions"):
                for d in (self.root / kind).iterdir() if (self.root / kind).exists() else []:
                    try:
                        m = json.loads((d / "meta.json").read_text())
                    except (OSError, ValueError):
                        continue
                    idx[m["id"]] = {"v": m["sha256"][:10], "sizes": sorted(int(s) for s in m.get("derivatives", {}))}
            self._index = idx
        return self._index

    def changed(self) -> None:
        self._index = None

    def store(self, eid: str, data: bytes, info: dict) -> dict:
        """Validate, keep the original, make the derivatives, write meta.json. Returns the meta."""
        if len(data) > 3 * 1024 * 1024:
            raise ValueError("artwork over 3 MB")
        try:
            im = Image.open(io.BytesIO(data))
            fmt = im.format
            im.load()
        except Exception as e:
            raise ValueError(f"not an image: {e.__class__.__name__}") from None
        if fmt not in ("PNG", "JPEG", "WEBP"):
            raise ValueError(f"format {fmt}")
        w, h = im.size
        if min(w, h) < 48 or max(w, h) > 4096:
            raise ValueError(f"unusable size {w}x{h}")
        d = self.dir(eid)
        d.mkdir(parents=True, exist_ok=True)
        ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
        for old in d.glob("original.*"):
            old.unlink()
        (d / f"original.{ext}").write_bytes(data)
        meta = {"id": eid, "type": "logo" if eid.startswith("comp:") else "crest", "licence": LICENCE, "attribution": "TheSportsDB",
                **info, "file": str((d / f"original.{ext}").relative_to(self.root)), "mime": f"image/{'jpeg' if ext == 'jpg' else ext}",
                "width": w, "height": h, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "retrieved": info.get("retrieved") or now_iso(), "checked": now_iso()}
        meta["derivatives"] = self.derive(eid, im)
        (d / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, sort_keys=True))
        m = self.misses()
        if m.pop(eid, None) is not None:
            self._write_json("misses.json", m)
        self.changed()
        self.gaps.resolve(eid, f"artwork from {meta.get('source', 'thesportsdb')} ({meta.get('source_name') or meta.get('source_id')})")
        return meta

    def derive(self, eid: str, im: Image.Image | None = None) -> dict:
        """Transparent WebP at each size, never larger than the original. Returns {size: [w, h]}."""
        if im is None:
            with Image.open(next(self.dir(eid).glob("original.*"))) as f:
                f.load()
                im = f.copy()
        im = im.convert("RGBA")
        out = {}
        dd = self.root / "derivatives" / ("competitions" if eid.startswith("comp:") else "teams") / slug(eid)
        dd.mkdir(parents=True, exist_ok=True)
        for s in SIZES:
            t = im.copy()
            t.thumbnail((s, s), Image.LANCZOS)          # no upscale: a 120 px crest stays 120 px
            t.save(dd / f"{s}.webp", "WEBP", quality=90, method=6)
            out[str(s)] = list(t.size)
        return out

    def derivative(self, eid: str, size: int) -> Path | None:
        if size not in SIZES:
            return None
        p = self.root / "derivatives" / ("competitions" if eid.startswith("comp:") else "teams") / slug(eid) / f"{size}.webp"
        if not p.exists() and self.meta(eid):
            self.derive(eid)
        return p if p.exists() else None

    def miss(self, eid: str, reason: str, tried: list[str], error: bool = False) -> None:
        m = self.misses()
        m[eid] = {"at": now_iso(), "reason": reason, "tried": tried, **({"error": True} if error else {})}
        self._write_json("misses.json", m)

    def forget_misses(self, ids=None) -> list[str]:
        """Drop miss records (all, or these) so the entities are looked up again on the next request."""
        m = self.misses()
        gone = [i for i in list(m) if ids is None or i in ids]
        for i in gone:
            m.pop(i)
        self._write_json("misses.json", m)
        return gone

    def clear(self, eid: str) -> None:
        """Forget one entity's artwork and miss record (a broken mapping): it is looked up again."""
        import shutil
        shutil.rmtree(self.dir(eid), ignore_errors=True)
        shutil.rmtree(self.root / "derivatives" / ("competitions" if eid.startswith("comp:") else "teams") / slug(eid), ignore_errors=True)
        m = self.misses()
        if m.pop(eid, None) is not None:
            self._write_json("misses.json", m)
        self.changed()

    def clear_derivatives(self) -> int:
        import shutil
        n = 0
        for kind in ("teams", "competitions"):
            for d in (self.root / "derivatives" / kind).iterdir():
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        return n

    def usage(self) -> dict:
        def size(p: Path) -> int:
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
        return {"originals": size(self.root / "teams") + size(self.root / "competitions"),
                "derivatives": size(self.root / "derivatives"), "total": size(self.root)}


# ------------------------------------------------------------------ the sources
class Source:
    """One request at a time, at least `interval` apart; 429 / 5xx back off and retry once.
    Artwork is only downloaded from the source's own image host."""
    name = ""
    interval = 1.0
    IMAGE = re.compile(r"^$")
    ua = UA

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.last = 0.0
        self.lock = asyncio.Lock()
        self.calls = 0

    async def get(self, url: str, params: dict | None = None) -> dict | None:
        """JSON from the source; None when it has no such record (404, empty or not JSON)."""
        async with self.lock:
            for attempt in range(2):
                wait = self.last + self.interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self.last = time.monotonic()
                self.calls += 1
                r = await self.client.get(url, params=params, timeout=20, headers=self.ua)
                if r.status_code in (429, 500, 502, 503) and attempt == 0:
                    await asyncio.sleep(30)
                    continue
                if r.status_code in (400, 404):
                    return None
                r.raise_for_status()
                try:
                    return r.json() if r.content.strip() else None
                except ValueError:
                    return None
        return None

    async def image(self, url: str) -> bytes:
        if not self.IMAGE.match(url or ""):
            raise ValueError(f"artwork URL outside {self.name}")
        r = await self.client.get(url, timeout=30, headers=self.ua)
        r.raise_for_status()
        return r.content


class TheSportsDB(Source):
    name = "thesportsdb"
    IMAGE = re.compile(r"^https://(r2|www)\.thesportsdb\.com/images/")

    @property
    def interval(self):
        return config.TSDB_INTERVAL

    async def api(self, path: str) -> dict:
        return await self.get(f"{config.TSDB_BASE}/{config.TSDB_KEY}/{path}") or {}


class ESPN(Source):
    name = "espn"
    BASE = "https://site.api.espn.com/apis/site/v2/sports"
    IMAGE = re.compile(r"^https://a\.espncdn\.com/i/(teamlogos|leaguelogos)/")   # never the generic sport icons
    ua = {"User-Agent": "signal-tv-art/1 (personal, non-commercial)"}       # its firewall refuses agents that carry a URL

    def __init__(self, client):
        super().__init__(client)
        self.interval = config.ESPN_INTERVAL
        self._lists: dict[str, tuple[float, list]] = {}

    async def teams(self, path: str) -> list[dict]:
        """A league's teams (kept for a day: one list serves every club of that league)."""
        hit = self._lists.get(path)
        if hit and time.time() - hit[0] < 86400:
            return hit[1]
        d = await self.get(f"{self.BASE}/{path}/teams")
        try:
            out = [t["team"] for t in d["sports"][0]["leagues"][0].get("teams", [])]
        except (KeyError, IndexError, TypeError):
            out = []
        self._lists[path] = (time.time(), out)
        return out

    async def team(self, path: str, tid: str) -> dict | None:
        d = await self.get(f"{self.BASE}/{path}/teams/{tid}")
        return (d or {}).get("team")

    async def league(self, path: str) -> dict | None:
        d = await self.get(f"{self.BASE}/{path}/scoreboard")
        return ((d or {}).get("leagues") or [None])[0]


class Wikidata(Source):
    name = "wikidata"
    API = "https://www.wikidata.org/w/api.php"
    COMMONS = "https://commons.wikimedia.org/w/api.php"
    IMAGE = re.compile(r"^https://(upload|thumb)\.wikimedia\.org/wikipedia/commons/")

    def __init__(self, client):
        super().__init__(client)
        self.interval = config.WIKI_INTERVAL

    async def items(self, ids: list[str], props: str = "labels|aliases|claims") -> dict:
        d = await self.get(self.API, {"action": "wbgetentities", "ids": "|".join(ids), "props": props, "languages": "en", "format": "json"})
        return {k: v for k, v in ((d or {}).get("entities") or {}).items() if "missing" not in v}

    async def search(self, term: str) -> list[str]:
        d = await self.get(self.API, {"action": "wbsearchentities", "search": term, "language": "en", "type": "item", "limit": 7, "format": "json"})
        return [x["id"] for x in (d or {}).get("search", [])]

    async def file(self, name: str) -> dict | None:
        """A Commons file: a raster URL (SVG rendered to PNG at 512 px), its page, licence and author."""
        d = await self.get(self.COMMONS, {"action": "query", "titles": f"File:{name}", "prop": "imageinfo", "format": "json",
                                          "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 512})
        page = next(iter(((d or {}).get("query") or {}).get("pages", {}).values()), {})
        ii = (page.get("imageinfo") or [None])[0]
        if not ii:
            return None
        em = ii.get("extmetadata") or {}
        meta = lambda k: re.sub(r"<[^>]+>", "", (em.get(k) or {}).get("value", "")).strip()   # noqa: E731
        raster = ii.get("mime") in ("image/png", "image/jpeg", "image/webp") and ii.get("width", 0) <= 1024
        return {"url": ii["url"] if raster else ii.get("thumburl", ""), "page": ii.get("descriptionurl", ""),
                "licence": meta("LicenseShortName") or meta("UsageTerms"), "author": meta("Artist"), "credit": meta("Credit")}


def _badge(x: dict) -> str:
    return x.get("strBadge") or x.get("strTeamBadge") or ""


def _found(url, source, sid, sname, api, how, tried, licence, attribution, page="", **match) -> dict:
    return {"url": url, "source": source, "source_id": sid, "source_name": sname, "api_url": api, "source_page": page,
            "licence": licence, "attribution": attribution, "match": {"method": how, "tried": tried, **match}}


async def find_tsdb(eid: str, ent: dict, src: TheSportsDB, ov: dict) -> tuple[dict | None, str, list[str]]:
    def out(rec, how, tried, path):
        return _found(_badge(rec), "thesportsdb", rec.get("idTeam") or rec.get("idLeague"), rec.get("strTeam") or rec.get("strLeague"),
                      f"{config.TSDB_BASE}/<key>/{path}", how, tried, LICENCE, "TheSportsDB", sport=rec.get("strSport"),
                      country=rec.get("strCountry"), league=rec.get("strLeague") if eid.startswith("team:") else None)
    if eid.startswith("comp:"):
        lid, country = (ov.get("id"), None) if ov.get("id") else LEAGUES.get(eid, (None, None))
        if not lid:
            return None, "no source id for this competition", []
        path = f"lookupleague.php?id={lid}"
        d = await src.api(path)
        lg = (d.get("leagues") or [None])[0]
        if not lg:
            return None, f"league {lid} not found", [lid]
        if ov.get("id"):
            return out(lg, "manual override", [lid], path), "", [lid]
        ok, how = verify_league(ent, lg, country)
        return (out(lg, how, [lid], path), "", [lid]) if ok else (None, how, [lid])
    if ov.get("id"):
        path = f"lookupteam.php?id={ov['id']}"
        d = await src.api(path)
        t = (d.get("teams") or [None])[0]
        return (out(t, "manual override", [ov["id"]], path), "", [ov["id"]]) if t else (None, f"team {ov['id']} not found", [ov["id"]])
    tried = []
    reason = "no candidates"
    for term in dict.fromkeys(ent["names"]):              # the shown name first, then strong aliases
        path = f"searchteams.php?{httpx.QueryParams({'t': term})}"
        tried.append(term)
        d = await src.api(path)
        t, how = match_team(ent, d.get("teams") or [])
        if t:
            return out(t, f"{how} (search '{term}')", tried, path), "", tried
        reason = how
        if len(tried) >= 4:
            break
    return None, reason, tried


async def find_espn(eid: str, ent: dict, src: ESPN, ov: dict) -> tuple[dict | None, str, list[str]]:
    def out(url, sid, sname, path, how, tried, **m):
        return _found(url, "espn", sid, sname, f"{ESPN.BASE}/{path}", how, tried, ESPN_LICENCE, "ESPN", path=path, **m)
    if eid.startswith("comp:"):
        path = ov.get("league") or ESPN_LEAGUES.get(eid)
        if not path:
            return None, "no source id for this competition", []
        lg = await src.league(path)
        if not lg:
            return None, f"league {path} not found", [path]
        url = espn_logo(lg.get("logos"))
        if not src.IMAGE.match(url):
            return None, "only a generic sport icon", [path]
        if not ov and not names_in(ent, [lg.get("name"), lg.get("shortName"), lg.get("abbreviation")]):
            return None, f"name {lg.get('name')}", [path]
        return out(url, lg.get("id"), lg.get("name"), path, "manual override" if ov else f"name ({lg.get('name')})", [path]), "", [path]
    if ov.get("league") and ov.get("id"):
        t = await src.team(ov["league"], ov["id"])
        if not t:
            return None, f"team {ov['id']} not found", [ov["id"]]
        return out(espn_logo(t.get("logos")), t["id"], t.get("displayName"), f"{ov['league']}/teams/{t['id']}", "manual override",
                   [ov["id"]], league=((t.get("defaultLeague") or {}).get("slug"))), "", [ov["id"]]
    national = ent["section"] == "national"
    tried: list[str] = []
    if national:
        for path in ESPN_NATIONAL:
            tried.append(path)
            t, how = match_espn_team(ent, await src.teams(path), True)
            if t:
                return out(espn_logo(t.get("logos")), t["id"], t.get("displayName"), f"{path}/teams/{t['id']}",
                           f"national team name, listed in {path.split('/')[1]}", tried), "", tried
        return None, "not listed in an international competition", tried
    country = CLUB_COUNTRY.get(eid)
    prefixes = ESPN_PREFIX.get(country or "")
    if not prefixes:
        return None, "no expected country for this club", []
    domestic = [f"soccer/{p}.{n}" for p in prefixes for n in (1, 2)]
    for path in domestic + list(ESPN_CONTINENTAL):
        teams = await src.teams(path)
        if not teams:
            continue
        tried.append(path)
        t, how = match_espn_team(ent, teams, False)
        if not t:
            if how.startswith("ambiguous"):
                return None, f"{how} in {path}", tried
            continue
        home = path.split("/")[1]
        if path not in domestic:
            # a continental list: the club's own league must be in the expected country
            detail = await src.team(path, t["id"]) or {}
            home = (detail.get("defaultLeague") or {}).get("slug") or ""
            if not any(home.startswith(p + ".") for p in prefixes):
                return None, f"{t.get('displayName')} plays in {home or 'an unknown league'} (expected {country})", tried
        return out(espn_logo(t.get("logos")), t["id"], t.get("displayName"), f"{path}/teams/{t['id']}",
                   f"name + listed in {path.split('/')[1]} + home league {home} ({country})", tried, league=home, country=country), "", tried
    return None, "name not listed in the country's leagues or a continental competition", tried


async def find_wikidata(eid: str, ent: dict, src: Wikidata, ov: dict) -> tuple[dict | None, str, list[str]]:
    async def out(item, how, tried, **m):
        logo = wd_logo(item)
        if not logo:
            return None, f"{item['id']} has no logo (P154)", tried
        f = await src.file(logo)
        if not f or not f["url"]:
            return None, f"Commons file '{logo}' not found", tried
        licence = f"{f['licence'] or 'licence not stated'} (Wikimedia Commons: {f['page']}); {TRADEMARK}"
        return _found(f["url"], "wikidata", item["id"], wd_names(item)[0] if wd_names(item) else item["id"],
                      f"https://www.wikidata.org/wiki/Special:EntityData/{item['id']}.json", how, tried, licence,
                      f["author"] or f["credit"] or "Wikimedia Commons", page=f["page"], file=logo, **m), "", tried
    qid = ov.get("qid") or (WIKIDATA_COMPS.get(eid) if eid.startswith("comp:") else None)
    if qid:
        item = (await src.items([qid])).get(qid)
        if not item:
            return None, f"item {qid} not found", [qid]
        if not ov.get("qid") and not names_in(ent, wd_names(item)):
            return None, f"label {wd_names(item)[:1]}", [qid]
        return await out(item, "manual override" if ov.get("qid") else "item id + label", [qid])
    if eid.startswith("comp:"):
        return None, "no item id for this competition", []
    if ent["section"] != "club":
        return None, "national teams: not from Wikidata", []        # their items rarely carry a usable crest
    country = CLUB_COUNTRY.get(eid)
    if not country:
        return None, "no expected country for this club", []
    want = _keys(ent["names"])
    tried, seen, ok = [], set(), {}
    for term in list(dict.fromkeys(ent["names"]))[:2]:
        tried.append(term)
        ids = [i for i in await src.search(term) if i not in seen]
        seen.update(ids)
        if not ids:
            continue
        items = await src.items(ids)
        clubs = [it for it in items.values() if WD_FOOTBALL_CLUB in wd_ids(it, "P31") and want & _keys(wd_names(it))]
        if not clubs:
            continue
        lands = await src.items(list({c for it in clubs for c in wd_ids(it, "P17")}), props="labels")
        label = lambda q: ((lands.get(q) or {}).get("labels", {}).get("en") or {}).get("value", "")   # noqa: E731
        for it in clubs:
            if any(same_country(country, label(c)) for c in wd_ids(it, "P17")):
                ok[it["id"]] = it
    if len(ok) == 1:
        it = next(iter(ok.values()))
        return await out(it, f"label/alias + association football club + country ({country})", tried, country=country)
    return None, (f"ambiguous: {len(ok)} items" if ok else "no football club item with that name and country"), tried


FINDERS = {"thesportsdb": find_tsdb, "espn": find_espn, "wikidata": find_wikidata}


def _pinned(ov: dict) -> str | None:
    """The source a manual override names (an override without one is TheSportsDB's)."""
    if ov.get("qid"):
        return "wikidata"
    if ov.get("id") or ov.get("league"):
        return ov.get("source") or "thesportsdb"
    return None


async def acquire(eid: str, lib: Library, src: TheSportsDB, persist: bool = True, more=()) -> dict | None:
    ents = entities()
    ent = ents.get(eid)
    if not ent:
        return None
    if eid.startswith("team:") and ent["section"] == "national" and ent["sport"] != "football":
        return None
    srcs = {"thesportsdb": src, **{s.name: s for s in more}}
    ov = lib.overrides().get(eid) or {}
    pinned = _pinned(ov)
    order = [pinned] if pinned else [n for n in config.ART_SOURCES if n in srcs]
    if pinned and pinned not in config.ART_SOURCES:           # a source switched off stays off, mapped or not
        order = []
        reasons_off = [f"{pinned}: mapped by override, but the source is not enabled (TVN_ART_SOURCES)"]
    else:
        reasons_off = []
    found, reasons, tried_all, errored = None, reasons_off, [], False
    if ov.get("none"):
        reasons.append("override: no artwork")
        order = []
    for name in order:
        if name not in srcs:
            reasons.append(f"{name}: source not enabled")
            continue
        try:
            found, reason, tried = await FINDERS[name](eid, ent, srcs[name], ov if pinned else {})
        except Exception as e:                                # source down: try again another day
            errored = True
            lib.log({"id": eid, "source": name, "result": "error", "error": f"{e.__class__.__name__}: {e}"[:200]})
            continue
        tried_all += [f"{name}: {t}" for t in tried]
        if found and not found["url"]:
            reason, found = "matched, but the source has no badge", None
        if found:
            break
        reasons.append(f"{name}: {reason}")
    if not found:
        reason = "; ".join(reasons + (["a source failed; tried again tomorrow"] if errored else [])) or "no source enabled"
        if persist:
            lib.miss(eid, reason, tried_all, error=errored)
        lib.log({"id": eid, "result": "miss", "reason": reason, "tried": tried_all})
        return None
    try:
        data = await srcs[found["source"]].image(found["url"])
    except Exception as e:
        lib.log({"id": eid, "source": found["source"], "result": "error", "error": f"image: {e.__class__.__name__}: {e}"[:200]})
        if persist:
            lib.miss(eid, f"{found['source']}: artwork download failed; tried again tomorrow", tried_all, error=True)
        return None
    info = {"name": ent["names"][0], "source_url": found.pop("url"), **found}
    if ov.get("note") and pinned:
        info["match"]["note"] = ov["note"]
    if not persist:
        return {"data": data, **info}
    meta = lib.store(eid, data, info)
    lib.log({"id": eid, "result": "cached", "source": info["source"], "source_id": info["source_id"],
             "method": info["match"]["method"], "bytes": len(data)})
    return meta


# ------------------------------------------------------------------ background queue
class Acquirer:
    """Deduplicated FIFO of entities to look up; one worker; nothing blocks a page."""

    def __init__(self, lib: Library, client: httpx.AsyncClient):
        self.lib = lib
        self.src = TheSportsDB(client)
        self.more = [ESPN(client), Wikidata(client)]
        self.q: asyncio.Queue[str] = asyncio.Queue()
        self.queued: set[str] = set()
        self.done = {"cached": 0, "miss": 0}
        self.task: asyncio.Task | None = None

    @property
    def calls(self) -> dict:
        return {s.name: s.calls for s in [self.src, *self.more]}

    def wanted(self, eid: str) -> bool:
        if eid in self.queued or eid in self.lib.index():
            return False
        if (self.lib.overrides().get(eid) or {}).get("none"):
            return False
        miss = self.lib.misses().get(eid)
        if miss:
            try:
                age = time.time() - datetime.strptime(miss["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            except (KeyError, ValueError):
                age = 1e9
            if age < (1 if miss.get("error") else config.ART_MISS_RETRY_DAYS) * 86400:
                return False
        return True

    def enqueue(self, ids) -> int:
        n = 0
        known = entities()
        for eid in ids:
            if eid in known and self.wanted(eid):
                self.queued.add(eid)
                self.q.put_nowait(eid)
                n += 1
        return n

    async def run(self) -> None:
        while True:
            eid = await self.q.get()
            try:
                meta = await acquire(eid, self.lib, self.src, more=self.more)
                self.done["cached" if meta else "miss"] += 1
            except Exception as e:                            # never let one entity stop the queue
                self.lib.log({"id": eid, "result": "error", "error": f"{e.__class__.__name__}: {e}"[:200]})
            finally:
                self.queued.discard(eid)

    async def refresh_old(self) -> int:
        """Re-check artwork older than ART_REFRESH_DAYS at its own source record; replace it if the source changed."""
        n = 0
        cutoff = time.time() - config.ART_REFRESH_DAYS * 86400
        srcs = {s.name: s for s in [self.src, *self.more]}
        ents = entities()
        for eid in list(self.lib.index()):
            m = self.lib.meta(eid) or {}
            try:
                checked = datetime.strptime(m.get("checked", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                checked = 0
            if checked > cutoff or eid not in ents:
                continue
            source = m.get("source", "thesportsdb")
            path = (m.get("match") or {}).get("path", "")
            ref = {"wikidata": {"qid": m.get("source_id")},
                   "espn": {"source": "espn", "league": path.split("/teams/")[0], "id": m.get("source_id") if eid.startswith("team:") else None}
                   }.get(source, {"source": "thesportsdb", "id": m.get("source_id")})
            try:
                found, _, _ = await FINDERS[source](eid, ents[eid], srcs[source], ref)
            except Exception as e:
                self.lib.log({"id": eid, "result": "error", "error": f"refresh: {e.__class__.__name__}: {e}"[:200]})
                continue
            if found and found["url"] and found["url"] != m.get("source_url"):
                data = await srcs[source].image(found["url"])
                self.lib.store(eid, data, {k: m[k] for k in ("name", "source", "source_id", "source_name", "api_url", "source_page",
                                                             "match", "licence", "attribution") if k in m} | {"source_url": found["url"]})
            else:
                m["checked"] = now_iso()
                (self.lib.dir(eid) / "meta.json").write_text(json.dumps(m, indent=1, ensure_ascii=False, sort_keys=True))
            n += 1
        return n


def prewarm_order() -> list[str]:
    """Competitions by prominence, then clubs, then national teams (football)."""
    ents = entities()
    comps = sorted((e for e in ents.values() if e["kind"] == "comp" and (e["key"] in LEAGUES or e["key"] in ESPN_LEAGUES
                                                                       or e["key"] in WIKIDATA_COMPS)), key=lambda e: -e["priority"])
    clubs = [e for e in ents.values() if e["section"] == "club"]
    nats = [e for e in ents.values() if e["section"] == "national"]
    return [e["key"] for e in comps + clubs + nats]


# ------------------------------------------------------------------ artwork-gap registry
class Gaps:
    """What the page actually drew with a generated crest or competition mark, one record per entity +
    artwork type (never one per render): first/last seen, how often, where (render contexts), the
    competition, why there was no artwork, and whether that has since been resolved. Resolved records
    stay (with their history), so a gap that keeps coming back is visible. Names the guide shows that
    have no canonical entry at all are kept as "name:<words>" (type "unlisted team").

    Counts are per page load per context (the page reports each fallback once), so a card repainted
    every minute doesn't run away with the ranking."""
    MAX = 5000
    CTX = re.compile(r"^[a-z]{2,12}(:[a-z-]{2,16})?$")

    def __init__(self, path: Path):
        self.path = path
        self.dirty = False
        try:
            self.data: dict = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    @staticmethod
    def art(eid: str) -> str:
        return "logo" if eid.startswith("comp:") else "crest"

    def record(self, eid: str, name: str, context: str, competition: str, reason: str, at: str | None = None) -> dict:
        at = at or now_iso()
        k = f"{eid}#{self.art(eid)}"
        g = self.data.get(k)
        if g is None:
            if len(self.data) >= self.MAX:          # full: the oldest resolved records go first
                for old in sorted((x for x in self.data.values() if x["status"] == "resolved"), key=lambda x: x["last_seen"])[:100]:
                    self.data.pop(f"{old['id']}#{old['artwork']}", None)
                if len(self.data) >= self.MAX:
                    return {}
            g = self.data[k] = {"id": eid, "name": name, "type": {"comp": "competition", "team": "team", "name": "unlisted team"}[eid.split(":")[0]],
                                "artwork": self.art(eid), "reason": reason, "first_seen": at, "last_seen": at, "count": 0,
                                "contexts": {}, "competitions": {}, "status": "open", "resolved_at": None, "resolved_by": None, "history": []}
        elif g["status"] == "resolved":
            g["status"], g["resolved_at"], g["resolved_by"] = "open", None, None
            g["history"].append({"at": at, "event": "reopened", "reason": reason})
            g["history"] = g["history"][-20:]
        g["name"] = name or g["name"]
        g["reason"] = reason
        g["last_seen"] = at
        g["count"] += 1
        if self.CTX.match(context or ""):
            g["contexts"][context] = g["contexts"].get(context, 0) + 1
        if competition:
            c = g["competitions"]
            c[competition[:60]] = c.get(competition[:60], 0) + 1
            if len(c) > 8:
                c.pop(min(c, key=c.get))
        self.dirty = True
        return g

    def resolve(self, eid: str, how: str, at: str | None = None) -> bool:
        g = self.data.get(f"{eid}#{self.art(eid)}")
        if not g or g["status"] != "open":
            return False
        at = at or now_iso()
        g["status"], g["resolved_at"], g["resolved_by"] = "resolved", at, how
        g["history"].append({"at": at, "event": "resolved", "how": how})
        g["history"] = g["history"][-20:]
        self.dirty = True
        return True

    def reconcile(self, index: dict) -> int:
        """Close open gaps that no longer are: artwork arrived some other way, or an unlisted name is
        now a canonical entity."""
        n = 0
        for g in list(self.data.values()):
            if g["status"] != "open":
                continue
            if g["id"] in index:
                n += self.resolve(g["id"], "artwork present in the library")
            elif g["id"].startswith("name:"):
                i, _, _ = sports.resolve_side(g["name"])
                if i >= 0:
                    n += self.resolve(g["id"], f"now a canonical entry: {sports.ENTITIES[i].key}")
        return n

    def flush(self) -> None:
        if not self.dirty:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False, sort_keys=True))
        os.replace(tmp, self.path)
        self.dirty = False

    def rows(self, kind: str = "", state: str = "open", sort: str = "seen") -> list[dict]:
        out = [g for g in self.data.values() if (state == "all" or g["status"] == state)
               and (not kind or (kind == "team" and g["type"] != "competition") or (kind == "comp" and g["type"] == "competition"))]
        key = (lambda g: g["last_seen"]) if sort == "recent" else (lambda g: (g["count"], g["last_seen"]))
        return sorted(out, key=key, reverse=True)


def gap_reason(lib: Library, eid: str, client_reason: str, queued: set[str] = frozenset()) -> str | None:
    """Why the page had no artwork for this entity (None: it isn't a gap - the library has it)."""
    if eid.startswith("name:"):
        return "no canonical entry in tvapp/sports.py (the name isn't a known team)"
    if client_reason == "load-failed":
        return "artwork file failed to load in the browser"
    if eid in lib.index():
        return None
    o = lib.overrides().get(eid) or {}
    if o.get("none"):
        return f"left without artwork on purpose: {o.get('note', 'override none')}"
    mi = lib.misses().get(eid)
    if mi:
        return f"no verified artwork: {mi.get('reason', '')}"
    if eid in queued:
        return "lookup queued"
    return "not looked up yet"


# ------------------------------------------------------------------ gaps report (iptv artwork missing)
def guide_gaps(events: list[dict]) -> tuple[collections.Counter, list[tuple[str, int, str, str]]]:
    """From the Sports guide: how often each canonical id appears, and the football team names that
    have no canonical entry at all (name, matches, example title, competition)."""
    seen: collections.Counter = collections.Counter()
    unknown: dict[str, list] = {}
    for e in events:
        seen.update([*(e.get("teams") or []), *([e["comp_id"]] if e.get("comp_id") else [])])
        if e.get("kind") != "match" or e.get("sport") != "football":
            continue
        m = sports.split_match(e.get("title") or "")
        for side in (m[1:3] if m else ()):
            i, key, _ = sports.resolve_side(side)
            if i >= 0:
                seen[sports.ENTITIES[i].key] += 0 if sports.ENTITIES[i].key in (e.get("teams") or []) else 1
                continue
            if not key or key.isdigit():
                continue
            row = unknown.setdefault(key, [sports._tidy(side), 0, e.get("title") or "", e.get("comp") or ""])
            row[1] += 1
    return seen, sorted(((r[0], r[1], r[2], r[3]) for r in unknown.values()), key=lambda r: (-r[1], r[0].lower()))


def missing(lib: Library, events: list[dict] | None = None, kind: str = "", state: str = "open", sort: str = "seen") -> dict:
    """The artwork-gap picture: coverage of the canonical dataset, the gaps the page actually drew
    (registry; kind team|comp, state open|resolved|all, sort seen|recent), canonical entities without
    artwork that haven't been on screen yet, and guide team names with no canonical entry."""
    ents = entities()
    idx, ov, misses = lib.index(), lib.overrides(), lib.misses()
    lib.gaps.reconcile(idx)
    lib.gaps.flush()
    seen, unknown = guide_gaps(events or [])
    shown = {g["id"] for g in lib.gaps.data.values()}
    quiet, deliberate = [], []
    cov = {"team": [0, 0], "comp": [0, 0]}
    for key, e in ents.items():
        o = ov.get(key) or {}
        if o.get("none"):
            deliberate.append({"id": key, "name": e["names"][0], "note": o.get("note", "")})
            continue
        cov[e["kind"]][1] += 1
        if key in idx:
            cov[e["kind"]][0] += 1
            continue
        if key in shown or (kind and e["kind"] != kind):
            continue
        mi = misses.get(key)
        sourceless = e["kind"] == "comp" and not (key in LEAGUES or key in ESPN_LEAGUES or key in WIKIDATA_COMPS or _pinned(o))
        quiet.append({"id": key, "name": e["names"][0], "sport": e["sport"], "in_guide": seen.get(key, 0),
                      "status": "miss" if mi else "no source record known (add an id to sportsart.py or overrides.json)"
                      if sourceless else "not looked up yet", "reason": (mi or {}).get("reason", "")})
    quiet.sort(key=lambda r: (-r["in_guide"], r["id"].split(":")[0] != "comp", r["id"]))
    pct = lambda a, b: round(100 * a / b, 1) if b else 100.0       # noqa: E731
    all_ = [cov["team"][0] + cov["comp"][0], cov["team"][1] + cov["comp"][1]]
    return {"at": now_iso(), "filters": {"kind": kind or "all", "state": state, "sort": sort},
            "coverage": {"teams": {"cached": cov["team"][0], "of": cov["team"][1], "pct": pct(*cov["team"])},
                         "competitions": {"cached": cov["comp"][0], "of": cov["comp"][1], "pct": pct(*cov["comp"])},
                         "all": {"cached": all_[0], "of": all_[1], "pct": pct(*all_)}},
            "gaps": lib.gaps.rows(kind, state, sort),
            "gaps_open": sum(g["status"] == "open" for g in lib.gaps.data.values()),
            "gaps_resolved": sum(g["status"] == "resolved" for g in lib.gaps.data.values()),
            "unresolved_not_shown": quiet, "deliberately_none": deliberate, "guide_checked": events is not None,
            "guide_unknown_teams": [] if kind == "comp" else
            [{"name": n, "matches": c, "example": t, "competition": comp} for n, c, t, comp in unknown]}


def _when(iso: str) -> str:
    return (iso or "")[:16].replace("T", " ")


def format_missing(r: dict, limit: int = 40) -> str:
    c, f = r["coverage"], r["filters"]
    out = [f"Sports artwork (/tv-test library) - {_when(r['at'])} UTC",
           f"Coverage: teams {c['teams']['cached']}/{c['teams']['of']} ({c['teams']['pct']}%), "
           f"competitions {c['competitions']['cached']}/{c['competitions']['of']} ({c['competitions']['pct']}%), "
           f"all {c['all']['cached']}/{c['all']['of']} ({c['all']['pct']}%)",
           f"Gap registry: {r['gaps_open']} open, {r['gaps_resolved']} resolved", ""]
    what = {"open": "Shown on screen without artwork", "resolved": "Resolved gaps", "all": "All recorded gaps"}[f["state"]]
    order = "most recent first" if f["sort"] == "recent" else "most seen first"
    kinds = {"team": "teams", "comp": "competitions"}.get(f["kind"], "teams and competitions")
    g = r["gaps"]
    out.append(f"{what} ({kinds}, {order}): {len(g)}" + ("" if g else " - nothing recorded yet"))
    for x in g[:limit]:
        ctx = ", ".join(f"{k} x{v}" for k, v in sorted(x["contexts"].items(), key=lambda kv: -kv[1])[:4])
        comps = ", ".join(sorted(x["competitions"], key=lambda k: -x["competitions"][k])[:3])
        state = f"resolved {_when(x['resolved_at'])}: {x['resolved_by']}" if x["status"] == "resolved" else x["reason"]
        again = sum(h["event"] == "reopened" for h in x["history"])
        out.append(f"  {x['count']:>4}x  {x['id']:<36} {x['name']} ({x['type']}, {x['artwork']})")
        out.append(f"         seen {_when(x['first_seen'])} .. {_when(x['last_seen'])}" + (f"; in {ctx}" if ctx else "")
                   + (f"; {comps}" if comps else "") + (f"; came back {again}x" if again else ""))
        out.append(f"         {state}")
    if len(g) > limit:
        out.append(f"  ... {len(g) - limit} more (--json for all)")
    if f["state"] == "open":
        q = r["unresolved_not_shown"]
        out += ["", f"Canonical entities without artwork, not drawn on screen yet: {len(q)}"]
        for x in q[:limit]:
            gd = f"  [in guide x{x['in_guide']}]" if x["in_guide"] else ""
            out.append(f"  {x['id']:<38} {x['name']}{gd}: {x['status']}" + (f" - {x['reason']}" if x["reason"] else ""))
        if len(q) > limit:
            out.append(f"  ... {len(q) - limit} more")
        if r["deliberately_none"] and f["kind"] != "comp":
            out += ["", "Left without artwork on purpose (override none):"]
            out += [f"  {x['id']:<38} {x['note']}" for x in r["deliberately_none"]]
        out.append("")
        if not r["guide_checked"]:
            out.append("Guide names: the live guide did not answer, so team names without a canonical entry are not listed.")
        elif r["guide_unknown_teams"]:
            u = r["guide_unknown_teams"]
            out.append(f"Football team names in today's/tomorrow's guide with no canonical entry: {len(u)} (top {min(limit, len(u))})")
            out.append("  (genuine clubs go into tvapp/sports.py DATA, their country into tvnext/sportsart.py; not every line is a team)")
            out += [f"  {x['matches']:>3}  {x['name']:<32} {x['competition'] or '-'}" for x in u[:limit]]
        elif f["kind"] != "comp":
            out.append("Football team names in the guide: all have a canonical entry.")
    out += ["", "Fix a wrong or missing mapping: add it to tvnext/overrides.json with a note saying how it was checked, then",
            "  curl -s 'http://127.0.0.1:8792/internal/refresh?id=<id>'"]
    return "\n".join(out) + "\n"
