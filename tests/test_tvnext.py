"""tvnext (the /tv-test sidecar): image derivatives and the sports artwork library.
Source records below are shaped like real TheSportsDB answers (fetched Oct 2026)."""
import asyncio
import io
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

try:
    from PIL import Image
except ImportError:                     # the app's own venv: the sidecar's (requirements-next.txt) has Pillow
    raise unittest.SkipTest("tvnext needs Pillow: run with /opt/signal-tv-next/venv/bin/python")

os.environ.setdefault("TVN_STATE", tempfile.mkdtemp())
os.environ.setdefault("TVN_CACHE", tempfile.mkdtemp())

from tvnext import config, fixtures, images, sportsart  # noqa: E402

ENTS = sportsart.entities()


def team(id_, name, country, sport="Soccer", gender="Male", league="", alt=None, short=None, badge="https://r2.thesportsdb.com/images/media/team/badge/x.png"):
    return {"idTeam": id_, "strTeam": name, "strTeamAlternate": alt, "strTeamShort": short, "strSport": sport, "strCountry": country,
            "strGender": gender, "strLeague": league, "strBadge": badge}


def png(w, h, alpha=True, fmt="PNG"):
    im = Image.new("RGBA" if alpha else "RGB", (w, h), (200, 30, 30, 128) if alpha else (200, 30, 30))
    b = io.BytesIO()
    im.save(b, fmt)
    return b.getvalue()


class Entities(unittest.TestCase):
    def test_dataset(self):
        teams = [e for e in ENTS.values() if e["kind"] == "team"]
        self.assertGreaterEqual(len(teams), 290)
        for k in ("team:bodo-glimt", "team:slavia-prague", "team:al-sadd", "team:cyprus"):
            self.assertIn(k, ENTS)
        self.assertEqual(ENTS["team:england"]["sport"], "football")              # national teams: football crests
        self.assertEqual(ENTS["team:bayern-munich"]["names"][0], "Bayern Munich")
        missing = [e["key"] for e in teams if e["section"] == "club" and e["key"] not in sportsart.CLUB_COUNTRY]
        self.assertEqual(missing, [], "every club has an expected country")


class TeamMatching(unittest.TestCase):
    def m(self, eid, cands):
        return sportsart.match_team(ENTS[eid], cands)

    def test_exact_club(self):
        t, how = self.m("team:arsenal", [team("133604", "Arsenal", "England", alt="Arsenal Football Club, AFC, Arsenal FC", league="English Premier League")])
        self.assertEqual(t["idTeam"], "133604")
        self.assertIn("country", how)

    def test_inter_milan_is_not_inter_miami(self):
        miami = team("135291", "Inter Miami", "United States", league="American Major League Soccer")
        milan = team("133681", "Inter Milan", "Italy", alt="Internazionale, FC Internazionale Milano", league="Italian Serie A")
        self.assertIsNone(self.m("team:inter-milan", [miami])[0])
        self.assertIsNone(self.m("team:inter-miami", [milan])[0])
        self.assertEqual(self.m("team:inter-milan", [miami, milan])[0]["idTeam"], "133681")

    def test_free_search_first_hits_are_refused(self):
        # what the free API really returned for short names
        self.assertIsNone(self.m("team:tottenham-hotspur", [team("140228", "Tottenham Women", "England", gender="Female", alt="Tottenham Hotspur")])[0])
        self.assertIsNone(self.m("team:tottenham-hotspur", [team("134899", "Austin Spurs", "United States", sport="Basketball")])[0])
        self.assertIsNone(self.m("team:inter-milan", [team("144244", "Intercity", "Spain")])[0])

    def test_barcelona_basketball_is_not_barcelona(self):
        basket = team("138000", "Barcelona", "Spain", sport="Basketball", alt="FC Barcelona Basquet")
        self.assertIsNone(self.m("team:barcelona", [basket])[0])
        self.assertEqual(self.m("team:barcelona", [basket, team("133739", "Barcelona", "Spain", alt="FC Barcelona")])[0]["idTeam"], "133739")

    def test_same_name_other_country(self):
        self.assertIsNone(self.m("team:rangers", [team("1", "Rangers", "Chile")])[0])

    def test_source_country_spelling(self):
        self.assertIsNotNone(self.m("team:feyenoord", [team("1", "Feyenoord", "The Netherlands", league="Dutch Eredivisie")])[0])

    def test_netball_namesake_refused(self):
        self.assertIsNone(self.m("team:nottingham-forest", [team("148600", "Nottingham Forest", "England", sport="Netball")])[0])

    def test_reserve_and_youth_sides(self):
        for name in ("Arsenal U21", "Arsenal Women", "Arsenal II", "Arsenal B"):
            self.assertIsNone(self.m("team:arsenal", [team("9", name, "England", alt="Arsenal")])[0], name)

    def test_national_team_vs_club(self):
        nat = team("133914", "England", "England", league="FIFA World Cup", alt="Angleterre")
        club = team("777", "England", "England", league="English Isthmian League")       # an imaginary club called England
        self.assertEqual(self.m("team:england", [nat])[0]["idTeam"], "133914")
        self.assertIsNone(self.m("team:england", [club])[0])

    def test_national_team_by_name_when_country_spelt_differently(self):
        t = team("1", "North Macedonia", "Macedonia", league="World Cup Qualifying UEFA")
        self.assertIsNotNone(self.m("team:north-macedonia", [t])[0])
        self.assertIsNone(self.m("team:north-macedonia", [team("2", "North Macedonia", "Macedonia", league="Macedonian First League")])[0])

    def test_two_confident_candidates_is_ambiguous(self):
        t, how = self.m("team:arsenal", [team("1", "Arsenal", "England"), team("2", "Arsenal", "England")])
        self.assertIsNone(t)
        self.assertIn("ambiguous", how)


class LeagueMatching(unittest.TestCase):
    def v(self, eid, lg, country):
        return sportsart.verify_league(ENTS[eid], lg, country)[0]

    def test_country_prefixed_names(self):
        self.assertTrue(self.v("comp:premier-league", {"strLeague": "English Premier League", "strSport": "Soccer", "strCountry": "England"}, "England"))
        self.assertTrue(self.v("comp:uefa-champions-league", {"strLeague": "UEFA Champions League", "strSport": "Soccer", "strCountry": "Europe"}, None))

    def test_country_spellings(self):
        self.assertTrue(self.v("comp:eredivisie", {"strLeague": "Dutch Eredivisie", "strSport": "Soccer", "strCountry": "The Netherlands"}, "Netherlands"))
        self.assertTrue(self.v("comp:fa-cup", {"strLeague": "FA Cup", "strSport": "Soccer", "strCountry": "United Kingdom"}, "England"))
        self.assertFalse(self.v("comp:eredivisie", {"strLeague": "Dutch Eredivisie", "strSport": "Soccer", "strCountry": "Belgium"}, "Netherlands"))

    def test_shipped_overrides_apply(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            self.assertEqual(lib.overrides()["comp:saudi-pro-league"]["id"], "4668")
            (lib.root / "overrides.json").write_text(json.dumps({"comp:saudi-pro-league": {"none": True}}))
            self.assertTrue(lib.overrides()["comp:saudi-pro-league"]["none"], "the Pi's own file wins")

    def test_wrong_league_refused(self):
        self.assertFalse(self.v("comp:premier-league", {"strLeague": "Scottish Premier League", "strSport": "Soccer", "strCountry": "Scotland"}, "England"))
        self.assertFalse(self.v("comp:premier-league", {"strLeague": "Premier League", "strSport": "Basketball", "strCountry": "England"}, "England"))
        self.assertFalse(self.v("comp:nba", {"strLeague": "Australian NBL", "strSport": "Basketball", "strCountry": "Australia"}, "United States"))


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = sportsart.Library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_keeps_original_metadata_and_transparent_derivatives(self):
        meta = self.lib.store("team:arsenal", png(512, 512), {"name": "Arsenal", "source": "thesportsdb", "source_id": "133604",
                                                              "source_url": "https://r2.thesportsdb.com/x.png", "match": {"method": "test"}})
        for k in ("id", "type", "source", "source_id", "source_url", "retrieved", "checked", "file", "mime", "width", "height",
                  "sha256", "derivatives", "match", "licence", "attribution"):
            self.assertIn(k, meta)
        self.assertEqual(meta["derivatives"], {"64": [64, 64], "128": [128, 128], "256": [256, 256]})
        d = Image.open(self.lib.derivative("team:arsenal", 128))
        self.assertEqual(d.mode, "RGBA")
        self.assertEqual(self.lib.index()["team:arsenal"]["sizes"], [64, 128, 256])

    def test_no_upscaling(self):
        meta = self.lib.store("team:fulham", png(100, 120), {"name": "Fulham", "source": "thesportsdb", "source_id": "1", "source_url": "u", "match": {}})
        self.assertEqual(meta["derivatives"]["256"], [100, 120])

    def test_bad_artwork_refused(self):
        for data in (b"<svg/>", png(20, 20), png(5000, 100)):
            with self.assertRaises(ValueError):
                self.lib.store("team:chelsea", data, {"name": "x"})
        self.assertNotIn("team:chelsea", self.lib.index())

    def test_derivatives_rebuilt_from_original(self):
        self.lib.store("team:everton", png(300, 300), {"name": "Everton", "source": "thesportsdb", "source_id": "1", "source_url": "u", "match": {}})
        self.lib.clear_derivatives()
        self.assertIsNotNone(self.lib.derivative("team:everton", 64))

    def test_clear_forgets_mapping(self):
        self.lib.store("team:everton", png(300, 300), {"name": "Everton", "source": "thesportsdb", "source_id": "1", "source_url": "u", "match": {}})
        self.lib.clear("team:everton")
        self.assertNotIn("team:everton", self.lib.index())


class Queue(unittest.TestCase):
    def test_dedupe_overrides_and_miss_retry(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            acq = sportsart.Acquirer(lib, client=None)
            (lib.root / "overrides.json").write_text(json.dumps({"team:wrexham": {"none": True}}))
            lib.miss("team:watford", "no candidates", ["Watford"])
            n = acq.enqueue(["team:arsenal", "team:arsenal", "team:wrexham", "team:watford", "team:not-real", "comp:premier-league"])
            self.assertEqual(n, 2)                                   # arsenal once, premier league; override + recent miss skipped
            self.assertEqual(sorted(acq.queued), ["comp:premier-league", "team:arsenal"])

    def test_old_miss_is_retried(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            (lib.root / "misses.json").write_text(json.dumps({"team:watford": {"at": "2020-01-01T00:00:00Z", "reason": "x"}}))
            self.assertEqual(sportsart.Acquirer(lib, client=None).enqueue(["team:watford"]), 1)


class FakeSource:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    async def api(self, path):
        self.calls.append(path)
        return self.answers.get(path.split("?")[0] + "?" + path.split("?")[1], {})

    async def image(self, url):
        return png(256, 256)


class Acquire(unittest.TestCase):
    def test_search_then_alias_then_store(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            src = FakeSource({"searchteams.php?t=Inter+Milan": {"teams": [team("133681", "Inter Milan", "Italy", league="Italian Serie A")]}})
            meta = asyncio.run(sportsart.acquire("team:inter-milan", lib, src))
            self.assertEqual(meta["source_id"], "133681")
            self.assertEqual(src.calls, ["searchteams.php?t=Inter+Milan"])
            self.assertIn("team:inter-milan", lib.index())

    def test_miss_is_recorded_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            src = FakeSource({"searchteams.php?t=Tottenham+Hotspur": {"teams": [team("140228", "Tottenham Women", "England", gender="Female")]},
                              "searchteams.php?t=Tottenham": {"teams": [team("140228", "Tottenham Women", "England", gender="Female")]},
                              "searchteams.php?t=Spurs": {"teams": [team("134899", "Austin Spurs", "United States", sport="Basketball")]}})
            self.assertIsNone(asyncio.run(sportsart.acquire("team:tottenham-hotspur", lib, src)))
            self.assertIn("team:tottenham-hotspur", lib.misses())
            self.assertNotIn("team:tottenham-hotspur", lib.index())

    def test_manual_override_id(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            (lib.root / "overrides.json").write_text(json.dumps({"team:wrexham": {"source": "thesportsdb", "id": "134000"}}))
            src = FakeSource({"lookupteam.php?id=134000": {"teams": [team("134000", "Wrexham AFC", "Wales")]}})
            meta = asyncio.run(sportsart.acquire("team:wrexham", lib, src))
            self.assertEqual(meta["match"]["method"], "manual override")


class Images(unittest.TestCase):
    def test_variants_never_upscale_and_keep_aspect(self):
        data, facts = images.render(png(1000, 563, alpha=False, fmt="JPEG"), "hero")
        self.assertEqual(facts["size"], (1000, 563))
        data, facts = images.render(png(3840, 2160, alpha=False, fmt="JPEG"), "hero")
        self.assertEqual(facts["size"], (1920, 1080))
        self.assertEqual(data[8:12], b"WEBP")

    def test_logo_keeps_transparency(self):
        data, _ = images.render(png(400, 400), "logo")
        self.assertEqual(Image.open(io.BytesIO(data)).mode, "RGBA")
        data, _ = images.render(png(400, 400), "logo", fmt="jpg")         # no WebP: PNG keeps alpha
        self.assertEqual(data[:4], b"\x89PNG")

    def test_hostile_sources_refused(self):
        with self.assertRaises(images.Refused):
            images.render(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "poster")
        with self.assertRaises(images.Refused):
            images.render(b"x" * (images.MAX_SOURCE + 1), "poster")
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 1000):
            with self.assertRaises(images.Refused):
                images.render(png(400, 400, alpha=False), "poster")      # "decompression bomb"

    def test_one_resize_per_image_and_cache_hits(self):
        calls = []

        class Resp:
            status_code = 200
            content = png(2000, 1125, alpha=False, fmt="JPEG")

        class Client:
            async def get(self, url, timeout=None):
                calls.append(url)
                await asyncio.sleep(0.05)
                return Resp()

        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "CACHE", Path(d)):
            async def go():
                c = Client()
                a, b = await asyncio.gather(images.get("hero-m", "ab" * 10, True, c), images.get("hero-m", "ab" * 10, True, c))
                again = await images.get("hero-m", "ab" * 10, True, c)
                return a, b, again
            a, b, again = asyncio.run(go())
            self.assertEqual(len(calls), 1, "two simultaneous requests, one source fetch, one resize")
            self.assertEqual(a, b)
            self.assertEqual(again, a)
            self.assertLess(a[0].stat().st_size, len(Resp.content))

    def test_bad_key_or_variant(self):
        for v, k in (("hero", "../etc/passwd"), ("huge", "ab" * 10)):
            with self.assertRaises(images.Refused):
                asyncio.run(images.get(v, k, True, None))

    def test_prune_oldest_first(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "CACHE", Path(d)):
            for i in range(10):
                p = images.path_for("poster", f"{i:02d}" * 10, "webp")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x" * 100_000)
                os.utime(p, (time.time() - 1000 + i, time.time() - 1000 + i))
            freed = images.prune(max_bytes=500_000)
            left = sorted(p.name for p in Path(d).rglob("*.webp"))
            self.assertGreaterEqual(freed, 500_000)
            self.assertIn("09" * 10 + ".webp", left, "newest kept")
            self.assertNotIn("00" * 10 + ".webp", left, "oldest gone")


def espn_team(id_, name, short=None, location=None, logos=None):
    return {"id": id_, "displayName": name, "shortDisplayName": short or name, "name": name, "location": location or name,
            "logos": logos if logos is not None else [{"href": f"https://a.espncdn.com/i/teamlogos/soccer/500/{id_}.png", "rel": ["full", "default"]}]}


class ESPNMatching(unittest.TestCase):
    def test_club_by_name_within_its_country(self):
        t, _ = sportsart.match_espn_team(ENTS["team:bodo-glimt"], [espn_team("1", "Aalesund"), espn_team("2", "Bodo/Glimt")], False)
        self.assertEqual(t["id"], "2", "Bodø = Bodo")
        t, _ = sportsart.match_espn_team(ENTS["team:basel"], [espn_team("3", "FC Basel")], False)
        self.assertEqual(t["id"], "3", "club-form words don't matter")

    def test_youth_side_and_ambiguity_refused(self):
        self.assertIsNone(sportsart.match_espn_team(ENTS["team:viking"], [espn_team("4", "Viking FK U19")], False)[0])
        t, why = sportsart.match_espn_team(ENTS["team:al-ain"], [espn_team("5", "Al Ain"), espn_team("6", "Al-Ain FC")], False)
        self.assertIsNone(t)
        self.assertIn("ambiguous", why)

    def test_national_team_exact_name_only(self):
        lst = [espn_team("7", "Netherlands U21"), espn_team("8", "Netherlands"), espn_team("9", "Northern Ireland")]
        self.assertEqual(sportsart.match_espn_team(ENTS["team:netherlands"], lst, True)[0]["id"], "8")
        self.assertEqual(sportsart.match_espn_team(ENTS["team:northern-ireland"], lst, True)[0]["id"], "9")

    def test_dark_logo_preferred_generic_icon_refused(self):
        logos = [{"href": "https://a.espncdn.com/i/leaguelogos/soccer/500/2200.png", "rel": ["full", "default"]},
                 {"href": "https://a.espncdn.com/i/leaguelogos/soccer/500-dark/2200.png", "rel": ["full", "dark"]}]
        self.assertIn("500-dark", sportsart.espn_logo(logos))
        icon = "https://a.espncdn.com/combiner/i?img=/redesign/assets/img/icons/ESPN-icon-tennis.png"
        self.assertIsNone(sportsart.ESPN.IMAGE.match(icon))


class Fake:
    """A source double: answers by URL (+ sorted params)."""
    def __init__(self, cls, answers):
        self.name, self.IMAGE, self.answers, self.calls = cls.name, cls.IMAGE, answers, []

    async def get(self, url, params=None):
        k = url + ("?" + "&".join(f"{a}={b}" for a, b in sorted(params.items())) if params else "")
        self.calls.append(k)
        return self.answers.get(k)

    async def image(self, url):
        assert self.IMAGE.match(url), url
        return png(256, 256)


class FakeESPN(Fake):
    def __init__(self, answers):
        super().__init__(sportsart.ESPN, answers)
        self._lists = {}

    BASE = sportsart.ESPN.BASE
    teams = sportsart.ESPN.teams
    team = sportsart.ESPN.team
    league = sportsart.ESPN.league


class FakeWikidata(Fake):
    def __init__(self, answers):
        super().__init__(sportsart.Wikidata, answers)

    API, COMMONS = sportsart.Wikidata.API, sportsart.Wikidata.COMMONS
    items = sportsart.Wikidata.items
    search = sportsart.Wikidata.search
    file = sportsart.Wikidata.file


def lst(*teams):
    return {"sports": [{"leagues": [{"teams": [{"team": t} for t in teams]}]}]}


E = sportsart.ESPN.BASE


class SourceChain(unittest.TestCase):
    def test_second_source_when_the_first_has_no_confident_match(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            tsdb = FakeSource({"searchteams.php?t=Al+Ittihad": {"teams": [team("1", "Al Ittihad", "Saudi Arabia", sport="Basketball")]}})
            espn = FakeESPN({f"{E}/soccer/ksa.1/teams": lst(espn_team("2276", "Al Ittihad"))})
            meta = asyncio.run(sportsart.acquire("team:al-ittihad", lib, tsdb, more=[espn]))
            self.assertEqual((meta["source"], meta["source_id"], meta["attribution"]), ("espn", "2276", "ESPN"))
            self.assertIn("ksa.1", meta["match"]["method"])
            self.assertIn("ESPN", meta["licence"])

    def test_continental_listing_needs_the_home_league(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            espn = FakeESPN({f"{E}/soccer/uefa.champions/teams": lst(espn_team("9", "Viking FK")),
                             f"{E}/soccer/uefa.champions/teams/9": {"team": {"id": "9", "defaultLeague": {"slug": "swe.1"}}}})
            self.assertIsNone(asyncio.run(sportsart.acquire("team:viking", lib, FakeSource({}), more=[espn])))
            self.assertIn("swe.1", lib.misses()["team:viking"]["reason"], "a namesake elsewhere is refused")
            espn.answers[f"{E}/soccer/uefa.champions/teams/9"] = {"team": {"id": "9", "defaultLeague": {"slug": "nor.1"}}}
            espn._lists.clear()
            self.assertEqual(asyncio.run(sportsart.acquire("team:viking", lib, FakeSource({}), more=[espn]))["source_id"], "9")

    def test_wikidata_competition_by_item_with_commons_licence(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            W = sportsart.Wikidata
            wd = FakeWikidata({
                f"{W.API}?action=wbgetentities&format=json&ids=Q617077&languages=en&props=labels|aliases|claims":
                    {"entities": {"Q617077": {"id": "Q617077", "labels": {"en": {"value": "UEFA Youth League"}},
                                              "claims": {"P154": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "UEFA Youth League.svg"}}}]}}}},
                f"{W.COMMONS}?action=query&format=json&iiprop=url|mime|size|extmetadata&iiurlwidth=512&prop=imageinfo&titles=File:UEFA Youth League.svg":
                    {"query": {"pages": {"1": {"imageinfo": [{"mime": "image/svg+xml", "width": 800, "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/UEFA_Youth_League.svg",
                     "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/UEFA_Youth_League.svg/512px-UEFA_Youth_League.svg.png",
                     "descriptionurl": "https://commons.wikimedia.org/wiki/File:UEFA_Youth_League.svg",
                     "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "Artist": {"value": "<a href='x'>UEFA</a>"}}}]}}}}})
            meta = asyncio.run(sportsart.acquire("comp:uefa-youth-league", lib, FakeSource({}), more=[wd]))
            self.assertEqual((meta["source"], meta["source_id"], meta["attribution"]), ("wikidata", "Q617077", "UEFA"))
            self.assertTrue(meta["source_url"].endswith(".png"), "SVG rendered to PNG by Commons")
            self.assertIn("Public domain", meta["licence"])
            self.assertEqual(meta["source_page"], "https://commons.wikimedia.org/wiki/File:UEFA_Youth_League.svg")

    def test_switched_off_source_stays_off_even_when_mapped(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "ART_SOURCES", ["thesportsdb", "wikidata"]):
            lib = sportsart.Library(Path(d))
            espn = FakeESPN({})
            self.assertIsNone(asyncio.run(sportsart.acquire("team:sabah", lib, FakeSource({}), more=[espn])))
            self.assertEqual(espn.calls, [])
            self.assertIn("not enabled", lib.misses()["team:sabah"]["reason"])

    def test_source_failure_backs_off_a_day(self):
        class Down(FakeESPN):
            async def get(self, url, params=None):
                raise RuntimeError("403")
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            self.assertIsNone(asyncio.run(sportsart.acquire("team:viking", lib, FakeSource({}), more=[Down({})])))
            self.assertTrue(lib.misses()["team:viking"]["error"])
            acq = sportsart.Acquirer(lib, client=None)
            self.assertEqual(acq.enqueue(["team:viking"]), 0, "not again on the next page view")
            m = lib.misses()
            m["team:viking"]["at"] = "2026-01-01T00:00:00Z"
            (lib.root / "misses.json").write_text(json.dumps(m))
            self.assertEqual(acq.enqueue(["team:viking"]), 1, "but tomorrow")

    def test_wikidata_logo_choice(self):
        item = {"claims": {"P154": [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "old.svg"}}, "qualifiers": {"P582": [{}]}},
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "new.svg"}}}]}}
        self.assertEqual(sportsart.wd_logo(item), "new.svg", "a logo with an end date is history")

    def test_manual_espn_override_pins_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sportsart.Library(Path(d))
            (lib.root / "overrides.json").write_text(json.dumps({"team:al-ittihad": {"source": "espn", "league": "soccer/ksa.1", "id": "2276", "note": "checked"}}))
            espn = FakeESPN({f"{E}/soccer/ksa.1/teams/2276": {"team": {"id": "2276", "displayName": "Al Ittihad", "logos": espn_team("2276", "x")["logos"]}}})
            tsdb = FakeSource({})
            meta = asyncio.run(sportsart.acquire("team:al-ittihad", lib, tsdb, more=[espn]))
            self.assertEqual(meta["match"]["method"], "manual override")
            self.assertEqual(meta["match"]["note"], "checked")
            self.assertEqual(tsdb.calls, [], "a pinned source is the only one asked")


class GapRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = sportsart.Library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_record_per_entity_and_counts(self):
        g = self.lib.gaps
        for ctx in ("sports:feature", "sports:board", "sports:board"):
            g.record("team:bodo-glimt", "Bodø/Glimt", ctx, "UEFA Champions League", "not looked up yet")
        g.record("comp:uefa-youth-league", "UEFA Youth League", "sports:compact", "", "no verified artwork")
        self.assertEqual(len(g.data), 2)
        r = g.data["team:bodo-glimt#crest"]
        self.assertEqual((r["count"], r["contexts"], r["type"], r["artwork"]), (3, {"sports:feature": 1, "sports:board": 2}, "team", "crest"))
        self.assertEqual(g.data["comp:uefa-youth-league#logo"]["type"], "competition")
        g.flush()
        self.assertEqual(len(sportsart.Gaps(self.lib.root / "gaps.json").data), 2, "persistent")

    def test_storing_artwork_resolves_and_a_return_reopens(self):
        self.lib.gaps.record("team:fulham", "Fulham", "sports:board", "", "not looked up yet")
        self.lib.store("team:fulham", png(128, 128), {"name": "Fulham", "source": "thesportsdb", "source_id": "1", "source_name": "Fulham", "source_url": "u", "match": {}})
        r = self.lib.gaps.data["team:fulham#crest"]
        self.assertEqual(r["status"], "resolved")
        self.assertIn("thesportsdb", r["resolved_by"])
        self.lib.gaps.record("team:fulham", "Fulham", "sports:board", "", "artwork file failed to load in the browser")
        self.assertEqual((r["status"], r["history"][-1]["event"]), ("open", "reopened"))
        self.assertEqual(len(self.lib.gaps.rows(state="all")), 1, "history kept on the one record")

    def test_reconcile_closes_unlisted_names_that_became_teams(self):
        self.lib.gaps.record("name:bodo glimt", "FK Bodø/Glimt", "sports:board", "", "no canonical entry")
        self.assertEqual(self.lib.gaps.reconcile({}), 1)
        self.assertIn("team:bodo-glimt", self.lib.gaps.data["name:bodo glimt#crest"]["resolved_by"])

    def test_reasons(self):
        self.assertIsNone(sportsart.gap_reason(self.lib, "team:fulham", "none") if self.lib.store(
            "team:fulham", png(64, 64), {"name": "F", "source": "thesportsdb", "source_id": "1", "source_url": "u", "match": {}}) else "x")
        self.assertIn("load", sportsart.gap_reason(self.lib, "team:fulham", "load-failed"))
        self.assertIn("on purpose", sportsart.gap_reason(self.lib, "team:west-indies", "none"))
        self.lib.miss("team:sabah", "espn: name not listed", [])
        self.assertIn("espn: name not listed", sportsart.gap_reason(self.lib, "team:sabah", "none"))
        self.assertEqual(sportsart.gap_reason(self.lib, "team:viking", "none", {"team:viking"}), "lookup queued")

    def test_report_ranks_and_filters(self):
        g = self.lib.gaps
        g.record("team:viking", "Viking FK", "sports:board", "", "x", at="2026-10-01T10:00:00Z")
        for _ in range(5):
            g.record("comp:uefa-youth-league", "UEFA Youth League", "sports:board", "", "y", at="2026-09-01T10:00:00Z")
        events = [{"kind": "match", "sport": "football", "title": "Agora Sim vs Viking", "teams": [], "comp": "X"}]
        r = sportsart.missing(self.lib, events)
        self.assertEqual([x["id"] for x in r["gaps"]], ["comp:uefa-youth-league", "team:viking"], "most seen first")
        self.assertEqual([x["id"] for x in sportsart.missing(self.lib, events, sort="recent")["gaps"]][0], "team:viking")
        self.assertEqual([x["id"] for x in sportsart.missing(self.lib, events, kind="team")["gaps"]], ["team:viking"])
        self.assertEqual([u["name"] for u in r["guide_unknown_teams"]], ["Agora Sim"])
        self.assertNotIn("team:viking", [x["id"] for x in r["unresolved_not_shown"]], "listed once")
        text = sportsart.format_missing(r)
        self.assertIn("Coverage: teams 0/", text)
        self.assertIn("5x  comp:uefa-youth-league", text)


class Fixtures(unittest.TestCase):
    """Live or replay from the real fixture date (a regional channel re-airing Saturday's game on
    Thursday, titled exactly like the live one)."""
    START = 1792076400                                    # Thu 15 Oct 2026 16:00 BST

    def test_verdict(self):
        v, S = fixtures.verdict, self.START
        self.assertEqual(v([S + 15 * 60], S), {"live": True}, "kick-off a quarter of an hour into the airing")
        self.assertEqual(v([S - 20 * 60], S), {"live": True}, "joined just after kick-off")
        sat = S - 5 * 86400 + 6 * 3600 - 2 * 3600         # Sat 10 Oct, 15:00 BST
        self.assertEqual(v([sat], S), {"replay": True, "played": sat})
        self.assertIsNone(v([S - 60 * 60], S), "an hour after kick-off: delayed, not certainly a replay")
        self.assertIsNone(v([S + 2 * 86400], S), "only a future fixture: no verdict")
        self.assertIsNone(v([S - 30 * 86400], S), "a meeting a month ago says nothing about today")
        self.assertIsNone(v([], S))
        self.assertEqual(v([sat, S + 10 * 60], S), {"live": True}, "the real one today wins")

    def test_ask_queues_then_answers_from_cache(self):
        class Src:
            def __init__(self):
                self.asked = []

            async def api(self, path):
                self.asked.append(path)
                if "Aston_Villa_vs_Brentford" in path:
                    return {"event": [{"strSport": "Soccer", "strTimestamp": "2026-10-10T14:00:00"}]}
                return {"event": None}

        with tempfile.TemporaryDirectory() as tmp:
            lib = sportsart.Library(Path(tmp) / "art")
            src = Src()
            fx = fixtures.Fixtures(lib, src, Path(tmp) / "fixtures.json")
            item = ("team:aston-villa", "team:brentford", self.START)
            self.assertEqual(fx.ask([item]), ({}, 1), "nothing known yet: queued")
            self.assertEqual(fx.ask([item]), ({}, 1), "asked twice, queued once")

            async def work():
                task = asyncio.create_task(fx.run())
                while fx.q.qsize() or fx.queued:
                    await asyncio.sleep(0.01)
                task.cancel()
            asyncio.run(work())
            self.assertTrue(any("Aston_Villa_vs_Brentford" in a for a in src.asked), src.asked)
            found, pending = fx.ask([item])
            sat = int(datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc).timestamp())
            self.assertEqual(found, {"team:aston-villa|team:brentford|1792076400": {"replay": True, "played": sat}})
            self.assertEqual(pending, 0)
            again = fixtures.Fixtures(lib, src, Path(tmp) / "fixtures.json")       # kept across restarts
            self.assertIn("team:aston-villa|team:brentford|1792076400", again.ask([item])[0])


if __name__ == "__main__":
    unittest.main()
