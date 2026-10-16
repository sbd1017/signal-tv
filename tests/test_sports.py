"""Sports names, aliases and events (tvapp/sports.py, epgsearch.Index): what matches, what must
not, and how one match under several titles becomes one event."""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tvapp import epgsearch, livemeta, server, sports
from tvapp.catalog import Catalogue
from tests.test_state_api import settings

NOW = 1_800_000_000
H = 3600
SPORT_CH = sports.OTHER


def row(start_h, hours, title, desc=""):
    return [int(NOW + start_h * H), int(NOW + (start_h + hours) * H), title, desc]


def kind(title, desc="", ch=SPORT_CH):
    info = sports.classify(title, desc, ch)
    return None if info is None else (sports.SPORT_KEYS[info.sport], {1: "match", 2: "event", 3: "show"}[info.kind])


class Aliases(unittest.TestCase):
    GUIDE = {
        "l_1": [row(-0.5, 2, "Premier League: Manchester United v Chelsea"), row(3, 2, "Champions League: Man Utd v Benfica")],
        "l_2": [row(-0.5, 2, "Spurs v Arsenal"), row(2, 2, "Serie A: Inter v Parma"),
                row(4, 2, "Paris SG vs Lyon - French Ligue 1"), row(6, 2, "Bundesliga: Bayern München - Dortmund")],
        "l_3": [row(-0.2, 2, "UEFA Champions League: Real Madrid v Juventus"),
                row(1, 2, "AFC Champions League Elite: Al Sadd v Esteghlal"), row(4, 1, "EHF Champions League: Kiel - Veszprem"),
                row(6, 1, "Global Champions League Equestrianism")],
        "l_4": [row(-0.5, 2, "Indian Premier League: Mumbai v Chennai"), row(2, 1, "Premier League Darts"),
                row(4, 2, "Formula 1: Singapore Grand Prix - Race"), row(7, 1, "UEFA Europa League: Roma v Porto")],
        "l_5": [row(0, 1, "NBA: Spurs v Lakers", "Basketball from San Antonio."), row(1, 1, "Inter Miami v Orlando City - MLS"),
                row(2, 1, "Manchester City v Brentford")],
        "l_film": [row(0, 2, "Festival Internazionale del Cinema", "Il festival internazionale."),
                   row(2, 2, "Kramer vs. Kramer"), row(4, 2, "Batman v Superman: Dawn of Justice")],
    }

    @classmethod
    def setUpClass(cls):
        cls.idx = epgsearch.Index(cls.GUIDE, NOW, channel_sport={f"l_{i}": SPORT_CH for i in range(1, 6)})

    def titles(self, q):
        return {e["title"] for e in self.idx.search(q, NOW)["events"]}

    def test_team_aliases_both_ways(self):
        for q in ("Man Utd", "Manchester United", "man united", "Man. Utd", "Manchester Utd"):
            self.assertEqual(self.titles(q), {"Manchester United vs Chelsea", "Manchester United vs Benfica"}, q)
        self.assertIn("Tottenham Hotspur vs Arsenal", self.titles("Tottenham"))
        self.assertIn("Tottenham Hotspur vs Arsenal", self.titles("Tottenham Hotspur"))
        for q in ("PSG", "Paris Saint-Germain", "Paris SG", "paris st germain"):
            self.assertIn("Paris Saint-Germain vs Lyon", self.titles(q), q)
        self.assertIn("Bayern Munich vs Borussia Dortmund", self.titles("Bayern Munich"))
        self.assertIn("Inter Milan vs Parma", self.titles("Inter Milan"))      # "Inter" as a whole side

    def test_competition_aliases(self):
        ucl = self.titles("UCL")
        self.assertIn("Real Madrid vs Juventus", ucl)
        self.assertIn("Manchester United vs Benfica", ucl)
        for other in ("Al Sadd vs Esteghlal", "Kiel vs Veszprem", "Global Champions League Equestrianism"):
            self.assertNotIn(other, ucl)                    # AFC / EHF / Global Champions League are other competitions
        self.assertIn("Al Sadd vs Esteghlal", self.titles("Champions League"))     # typed as written: literal, as before
        epl = self.titles("EPL")
        self.assertIn("Manchester United vs Chelsea", epl)
        self.assertNotIn("Mumbai vs Chennai", epl)          # Indian Premier League
        self.assertNotIn("Premier League Darts", epl)
        self.assertEqual(self.titles("F1"), self.titles("Formula 1"))
        self.assertIn("AS Roma vs FC Porto", self.titles("Europa League"))
        self.assertIn("AS Roma vs FC Porto", self.titles("UEFA Europa League"))

    def test_no_false_positives(self):
        for q in ("United", "City", "Real", "Madrid"):
            self.assertEqual(sports.query_groups(sports.norm(q).split()), [], q)          # never names on their own
        self.assertNotIn("Manchester City vs Brentford", self.titles("Man Utd"))
        self.assertNotIn("Spurs vs Lakers", self.titles("Tottenham"))                    # basketball's Spurs
        inter = self.titles("Inter Milan")
        self.assertNotIn("Festival Internazionale del Cinema", inter)                   # Italian for "international"
        self.assertNotIn("Inter Miami vs Orlando City", inter)
        self.assertEqual(self.titles("manchester unted"), set())                         # nothing fuzzy

    def test_query_text_is_kept(self):
        self.assertEqual([(a, b) for a, b, _ in sports.query_groups("man utd v chelsea".split())], [(0, 2), (3, 4)])


class Recognition(unittest.TestCase):
    def test_match_title_styles(self):
        for t in ("Arsenal vs Leeds", "Arsenal v Leeds United", "Arsenal - Leeds", "Arsenal / Leeds",
                  "Arsenal vs Leeds United – English Premier League 2026/2027 - Week 6", "PL 26/27: Arsenal v Leeds",
                  "Nogomet (M): Arsenal - Leeds, Premier liga 2026/2027", "LIVE: Arsenal v Leeds United",
                  "Premier League: Arsenal-Leeds Etapa 6"):
            info = sports.classify(t, "", SPORT_CH)
            self.assertEqual((info.kind, info.key), (sports.MATCH, sports.classify("Arsenal v Leeds", "", SPORT_CH).key), t)

    def test_not_matches(self):
        self.assertIsNone(kind("Kramer vs. Kramer", ch=0))
        self.assertIsNone(kind("Batman v Superman: Dawn of Justice", ch=0))
        self.assertIsNone(kind("Policie v akci", ch=0))                                  # Czech "v" = "in"
        self.assertIsNone(kind("La Aceitera, contra corriente", ch=0))
        self.assertNotEqual(kind("Arsenal: All or Nothing", "A documentary following the club."), ("football", "match"))
        self.assertNotEqual((kind("MATCH HIGHLIGHTS 26/27 MW06 Sunderland v Brighton") or ("", ""))[1], "match")
        self.assertNotEqual((kind("Super Sunday: Arsenal v Chelsea build-up") or ("", ""))[1], "match")
        self.assertEqual(kind("PL Greatest Games: ManU v Spurs '09"), ("football", "show"))
        self.assertEqual(kind("Mundial F1 - GP de Emilia Romagna")[1], "show")          # not a pair of teams

    def test_sport_words_decide(self):
        self.assertEqual(kind("Košarka: Španska liga: Barcelona - Valencia"), ("basketball", "match"))
        self.assertEqual(kind("Am. nogomet (M): Packers - C. Bears, NFL 2026/2027"), ("nfl", "match"))
        self.assertEqual(kind("Rukomet - Njemačka liga: Kiel - Hamburg"), ("handball", "match"))
        self.assertEqual(kind("Boks: Ben Whittaker - Vladimir Belujsky"), ("boxing", "match"))
        self.assertEqual(kind("Int CRI '26: IND v WI 3rd T20"), ("cricket", "match"))
        self.assertEqual(kind("Esteghlal FC (IRN) vs Al Sadd (QAT) - AFC Champions League Elite 2026/2027"), ("football", "match"))
        self.assertEqual(kind("UFC Fight Night: Allen vs Duncan"), ("mma", "match"))

    def test_seen_on_the_real_guide(self):
        self.assertEqual(kind("Formel 1: Rennen - GP Singapur"), ("f1", "event"))           # not "Rennen vs GP Singapur"
        info = sports.classify("Rugby: Georgia v Italy", "World Rugby Junior World Championship 2026.", SPORT_CH)
        self.assertEqual((sports.SPORT_KEYS[info.sport], info.comp), ("rugby", -1))          # not the EFL Championship
        info = sports.classify("UEFA Champions League", "LIVE From Arsenal Stadium - London, England.", SPORT_CH)
        self.assertNotEqual(getattr(info, "kind", 0), sports.MATCH)                          # England is a place here
        self.assertNotEqual(kind("Infinitamente Sinner: Ancora Wimbledon"), ("tennis", "event"))   # a documentary
        self.assertEqual(kind("LIVE: WTA 1000 Wuhan"), ("tennis", "event"))
        # "Championship" alone is the EFL Championship only when nothing says another sport, and
        # "Race 1" / "Heat 2" are never teams (truck racing at Jarama showed up as a football match)
        for t in ("FIA European Truck Racing Championship: Race 1 - Jarama", "British Touring Car Championship: Race 3 - Brands Hatch",
                  "American League Championship Series: Tampa Bay Rays vs Cleveland Guardians"):
            info = sports.classify(t, "", SPORT_CH)
            self.assertFalse(info and info.kind == sports.MATCH and info.sport == sports.FOOTBALL, t)
            self.assertFalse(info and info.comp >= 0 and sports.ENTITIES[info.comp].key == "comp:efl-championship", t)
        info = sports.classify("World Rallycross Championship: Heat 2 - Lohéac", "", SPORT_CH)
        self.assertFalse(info and info.kind == sports.MATCH, "a heat is not a team")
        for t in ("Championship: Leeds United v Burnley", "Sky Bet Championship: Leeds v Burnley"):
            info = sports.classify(t, "", SPORT_CH)
            self.assertEqual((sports.SPORT_KEYS[info.sport], info.kind, sports.ENTITIES[info.comp].key),
                             ("football", sports.MATCH, "comp:efl-championship"), t)
        # a club whose name ends in a women's marker word ("noi") is that club, men's side
        self.assertEqual(sports.resolve_side("Cong An Ha Noi")[1:], ("team:cong-an-ha-noi", False))
        self.assertEqual(sports.resolve_side("Kashima Antlers (W)".replace("(W)", "W"))[1:], ("team:kashima-antlers", True))
        # guide spellings of clubs added in the artwork completion pass
        for side, key in (("FK Bodø/Glimt", "team:bodo-glimt"), ("Σλάβια Πράγας", "team:slavia-prague"), ("Inter Mediolan", "team:inter-milan"),
                          ("Lech Poznań", "team:lech-poznan"), ("Kyoto Sanga F.C.", "team:kyoto-sanga"), ("Ίντερ", "team:inter-milan")):
            self.assertEqual(sports.resolve_side(side)[1], key, side)

    def test_competition_where_the_guide_puts_it(self):
        def comp(title, desc=""):
            info = sports.classify(title, desc, SPORT_CH)
            return sports.ENTITIES[info.comp].key if info and info.comp >= 0 else None
        # after the teams, and in other languages
        self.assertEqual(comp("Nogomet (M): West Brom - Birmingham, Championship 2026/2027"), "comp:efl-championship")
        self.assertEqual(comp("UNION SG - REAL SOCIEDAD", "EUROPA LIGA."), "comp:uefa-europa-league")
        self.assertEqual(comp("Piłka nożna: Liga Konferencji UEFA - mecz finałowy: Crystal Palace FC - Rayo Vallecano"),
                         "comp:uefa-conference-league")
        # the third tier is not the Bundesliga
        self.assertEqual(comp("Nogomet - 3. Bundesliga: Fortuna Koln - Stuttgart II"), "comp:3-liga")
        self.assertEqual(comp("Bundesliga: Bayern v Dortmund"), "comp:bundesliga")
        self.assertIsNone(comp("Rugby: Leinster v Munster, Champions Cup"))
        # the Saudi league by its Croatian and Portuguese names, its clubs by their short names
        self.assertEqual(comp("Nogomet - Saudijska liga: Riyadh - Hilal"), "comp:saudi-pro-league")
        self.assertEqual(comp("Liga Arábia Saudita 2026-27 - Al Riyadh x Al-Hilal"), "comp:saudi-pro-league")
        info = sports.classify("Nogomet - Saudijska liga: Riyadh - Hilal", "", SPORT_CH)
        self.assertEqual([sports.ENTITIES[t].key for t in info.teams], ["team:al-riyadh", "team:al-hilal"])
        info = sports.classify("Al Hilal Omdurman vs Sidama Coffee", "", SPORT_CH)
        self.assertFalse(info and sports.BY_ID_KEY["team:al-hilal"].id in info.teams, "Sudan's Al Hilal is another club")
        # a classic re-shown
        self.assertTrue(sports.classify("Retro EFL Cup 09", "Relive the 2009 League Cup final between Manchester United and Tottenham.",
                                        SPORT_CH).replay)

    def test_variants_kept_apart(self):
        key = lambda t: sports.classify(t, "", SPORT_CH).key
        self.assertNotEqual(key("UEFA Youth League: Leipzig vs PSV"), key("RB Leipzig vs PSV"))
        self.assertNotEqual(key("Serie A (W): Fiorentina v Sassuolo"), key("Serie A: Fiorentina v Sassuolo"))
        self.assertNotEqual(key("Benfica B x FC Felgueiras"), key("Benfica x FC Felgueiras"))
        self.assertTrue(sports.classify("WSL 26/27: Chelsea v Arsenal", "", SPORT_CH).women)
        self.assertEqual(key("Atlético vs Manchester United - Champions League"), key("Atletico Madrid v Man Utd"))
        self.assertEqual(key("A Madrid vs Manchester United"), key("Atletico Madrid v Man Utd"))
        self.assertNotEqual(key("Atletico Mineiro v Flamengo"), key("Atletico Madrid v Flamengo"))
        youth = sports.classify("Leipzig vs PSV", "UEFA Youth League, matchday 2.", SPORT_CH)
        self.assertTrue(youth.youth)
        self.assertNotEqual(youth.key, key("RB Leipzig vs PSV - UEFA Champions League"))


class Events(unittest.TestCase):
    GUIDE = {
        # one match, four broadcasters, four titles, 19:55 / 20:00 / 20:05 starts
        "l_tnt1": [row(-0.5, 2.25, "Live Premier League: Arsenal v Chelsea"), row(-1, 0.5, "Arsenal v Chelsea build-up")],
        "l_bein1": [row(-0.58, 2.2, "Arsenal vs Chelsea - English Premier League 2026/2027 - Week 6")],
        "l_ss": [row(-0.42, 2.0, "PL 26/27: Arsenal v Chelsea")],
        "l_nova": [row(-0.5, 2.0, "Nogomet (M): Arsenal - Chelsea, Premier liga 2026/2027"),
                   row(6, 2, "Nogomet (M): Arsenal - Chelsea, Premier liga 2026/2027")],     # replay later
        "l_hd": [row(1, 2, "HULL CITY - EVERTON 11/10/26")],                                     # an old match again
        "l_bk": [row(2, 2, "Košarka: Španska liga: Barcelona - Valencia"), row(5, 1, "F1 Race Highlights")],
        "l_ar": [row(2, 2, "Barcelona - Valencia")],                                            # the same basketball game
        "l_f1": [row(3, 2, "Formula 1: Singapore Grand Prix - Race")],
        "l_f1b": [row(3.05, 2, "F1 Main Race - Singapore Grand Prix")],
        "l_acl": [row(-1, 2, "Esteghlal FC (IRN) vs Al Sadd (QAT) - AFC Champions League Elite")],
        "l_film": [row(0, 2, "Kramer vs. Kramer")],
    }

    def setUp(self):
        chs = {i: SPORT_CH for i in self.GUIDE if i != "l_film"}
        self.idx = epgsearch.Index(self.GUIDE, NOW, channel_sport=chs)
        self.ev = self.idx.sports(NOW, NOW, NOW + 12 * H)

    def find(self, title):
        return [e for e in self.ev if e["title"] == title]

    def test_one_match_one_card(self):
        live = self.find("Arsenal vs Chelsea")
        self.assertEqual(len(live), 2)                     # on now, and the replay at +6 h
        now = next(e for e in live if e["when"] == "live")
        self.assertEqual(sorted(now["ids"]), ["l_bein1", "l_nova", "l_ss", "l_tnt1"])
        self.assertEqual((now["comp"], now["sport"], now["replay"], now["live_tag"]), ("Premier League", "football", False, True))
        later = next(e for e in live if e["when"] != "live")
        self.assertEqual((later["ids"], later["replay"]), (["l_nova"], True))
        self.assertEqual(self.ev[0]["title"], "Arsenal vs Chelsea")                     # the big match first

    def test_build_up_and_highlights_are_not_cards(self):
        titles = {e["title"] for e in self.ev}
        self.assertNotIn("Arsenal v Chelsea build-up", titles)
        self.assertNotIn("F1 Race Highlights", titles)
        self.assertNotIn("Kramer vs. Kramer", titles)

    def test_replays_and_sports(self):
        self.assertTrue(self.find("Hull City vs Everton")[0]["replay"])
        bk = self.find("Barcelona vs Valencia")
        self.assertEqual([(e["sport"], sorted(e["ids"])) for e in bk], [("basketball", ["l_ar", "l_bk"])])
        f1 = [e for e in self.ev if e["sport"] == "f1"]
        self.assertEqual([sorted(e["ids"]) for e in f1], [["l_f1", "l_f1b"]])
        acl = self.find("Esteghlal vs Al Sadd")                  # both known now: the cards use their names
        self.assertEqual((acl[0]["comp"], acl[0]["sport"]), ("AFC Champions League", "football"))


class Replays(unittest.TestCase):
    def test_whole_earlier_airing_makes_a_replay(self):
        guide = {"l_sky": [row(-3, 2, "Live Monday Night Football: Coventry v Newcastle")],    # 20:00-22:00, ended
                 "l_bein": [row(-0.5, 2, "Coventry vs Newcastle United - English Premier League")],   # 22:30 again
                 "l_8k": [row(-4, 0.5, "Liverpool vs Manchester City - English Premier League"),     # condensed, ended
                          row(-0.5, 2, "Liverpool vs Manchester City - English Premier League")]}
        idx = epgsearch.Index(guide, NOW, channel_sport={k: SPORT_CH for k in guide})
        ev = {e["title"]: e for e in idx.sports(NOW, NOW, NOW + 6 * H)}
        self.assertTrue(ev["Coventry City vs Newcastle United"]["replay"])
        self.assertFalse(ev["Liverpool vs Manchester City"]["replay"])        # a 30-minute version earlier doesn't count
        self.assertEqual([e["title"] for e in idx.search("Coventry", NOW)["events"]], ["Coventry City vs Newcastle United"])

    def test_live_tag_wins(self):
        guide = {"l_a": [row(-3, 2, "Atletico Madrid v Manchester United - Champions League")],
                 "l_b": [row(-0.5, 2, "LIVE Champions League: Atletico Madrid-Manchester United")],
                 "l_y": [row(-3, 2, "Piłka nożna: Liga Młodzieżowa UEFA - mecz: Atletico Madryt - Manchester United FC")]}
        idx = epgsearch.Index(guide, NOW, channel_sport={k: SPORT_CH for k in guide})
        ev = idx.sports(NOW, NOW, NOW + 6 * H)
        self.assertEqual([(e["ids"], e["replay"]) for e in ev], [(["l_b"], False)])
        self.assertTrue(sports.classify(guide["l_y"][0][2], "", SPORT_CH).youth)

    def test_build_up_listings_and_late_starters_are_one_airing(self):
        t = "Galatasaray v Barcelona - UEFA Champions League"
        guide = {"l_early": [row(1, 3, t)], "l_k1": [row(2, 2, t)], "l_k2": [row(2, 2, t)], "l_late": [row(3, 1, t)],
                 "l_rep": [row(4, 2, t)], "l_night": [row(8, 2.5, t)]}
        idx = epgsearch.Index(guide, NOW, channel_sport={k: SPORT_CH for k in guide})
        ev = sorted(idx.sports(NOW, NOW, NOW + 12 * H), key=lambda e: e["start"])
        self.assertEqual([(sorted(e["ids"]), e["start"] - NOW, e["replay"]) for e in ev],
                         [(["l_early", "l_k1", "l_k2", "l_late"], 2 * H, False), (["l_rep"], 4 * H, True),
                          (["l_night"], 8 * H, True)])
        self.assertEqual(len(idx.search("galatasaray", NOW)["events"]), 3)

    def test_tomorrow_knows_tonight(self):
        guide = {"l_a": [row(1, 2, "Chelsea v Bournemouth - Premier League")], "l_b": [row(26, 2, "Chelsea v Bournemouth - Premier League")]}
        idx = epgsearch.Index(guide, NOW, horizon=40 * H, channel_sport={k: SPORT_CH for k in guide})
        tomorrow = idx.sports(NOW, NOW + 24 * H, NOW + 48 * H)
        self.assertEqual([(e["ids"], e["replay"]) for e in tomorrow], [(["l_b"], True)])


class Endpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        s = settings(Path(self.tmp.name))
        server.S.settings = s
        server.S.cat = Catalogue(s, None)
        names = {"l_tnt1": "UK: TNT SPORTS 1 ᴴᴰ", "l_bein1": "UK: BEIN SPORTS 1 ENGLISH ᴿᴬᵂ", "l_ss": "DSTV: SUPERSPORT PL HD",
                 "l_nova": "HR: SPORT KLUB 1 ᴴᴰ", "l_film": "UK: FILM4 HD"}
        server.S.cat.data["live"] = [{"id": i, "name": n, "cat": "c", "url": "u"} for i, n in names.items()]
        server.S.cat.data["cats"]["live"] = {"c": "UK| SPORT"}
        server.S.cat._index()
        server.S.cat.guide.data = {k: v for k, v in Events.GUIDE.items() if k in names}
        server.S.cat.guide.updated = NOW
        server.S.live_meta = livemeta.MetaCache(Path(self.tmp.name) / "lm.json")
        server.S.live_meta.put("l_tnt1", {"v": "hevc", "bits": 10, "h": 2160, "w": 3840, "fps": 50.0}, "probe")
        server.S.vindex = None
        server.S.epg_index = None
        server.S.epg_index_task = None
        server.S.tasks = set()
        server.S.sports_cache = {}
        self.c = TestClient(server.app)
        self._t = epgsearch.time.time, server.time.time
        epgsearch.time.time = server.time.time = lambda: NOW

    def tearDown(self):
        epgsearch.time.time, server.time.time = self._t
        self.tmp.cleanup()

    def test_sports_page(self):
        d = self.c.get("/tv/api/sports", params={"caps": "avc.2160.60.s,hevc10.2160.60.s", "tzo": "60"}).json()
        top = d["events"][0]
        self.assertEqual((top["title"], top["when"], top["comp"]), ("Arsenal vs Chelsea", "live", "Premier League"))
        self.assertEqual(top["channels"][0]["id"], "l_tnt1")                 # 4K HEVC known smooth here: first
        self.assertTrue(top["channels"][0]["label"].startswith("4K 50fps"))
        self.assertEqual(d["counts"]["football"], 2)                         # the match and its replay
        no_hevc = self.c.get("/tv/api/sports", params={"caps": "avc.1080.60.s"}).json()["events"][0]
        self.assertNotEqual(no_hevc["channels"][0]["id"], "l_tnt1")         # a 4K HEVC feed isn't first without HEVC
        self.assertEqual(self.c.get("/tv/api/sports", params={"day": "tomorrow"}).status_code, 200)


class GreekSides(unittest.TestCase):
    """Greek guides name foreign clubs and countries in Greek: by the Greek names in the dataset, or by
    sound (transliterated, then matched against the Latin names), and only to one clear candidate."""

    def test_greek_names(self):
        for side, key in (("Ρεάλ Μαδρίτης", "team:real-madrid"), ("Κολωνία", "team:1-fc-koln"), ("Αμβούργο", "team:hamburger-sv"),
                          ("Βέρντερ Βρέμης", "team:werder-bremen"), ("Ισπανία", "team:spain"), ("Ομόνοια", "team:omonia-nicosia"),
                          ("Βιλερμπάν", "team:asvel"), ("Ντένβερ Μπρόνκος", "team:denver-broncos")):
            self.assertEqual(sports.resolve_side(side)[1], key, side)

    def test_nfl_in_greek(self):
        for side, key in (("Σιάτλ Σίχοκς", "team:seattle-seahawks"), ("Κάνσας Σίτι Τσιφς", "team:kansas-city-chiefs"),
                          ("Νέα Υόρκη Τζετς", "team:new-york-jets")):
            self.assertEqual(sports.resolve_side(side, sports.NFL)[1], key, side)


class SportFromDescription(unittest.TestCase):
    def test_nicknames_once_the_description_names_the_sport(self):
        full = sports.classify("NFL: Denver Broncos vs Seattle Seahawks", "", SPORT_CH)
        nick = sports.classify("Seahawks vs Broncos", "NFL Football. Week 7 of the regular season.", SPORT_CH)
        self.assertEqual((nick.sport, nick.key), (sports.NFL, full.key), "the same game: one card")


class NotMatches(unittest.TestCase):
    def test_wrap_up_shows_and_f1_features(self):
        for title, ch, why in (("Boxing: Sunday of Pain - Podsumowanie", SPORT_CH, "Polish: summary"),
                               ("F1: Brad Pitt vs McLaren", SPORT_CH, "F1 has no head-to-heads"), ("Brad Pitt vs McLaren", sports.F1, "")):
            info = sports.classify(title, "", ch)
            self.assertTrue(info is None or info.kind != sports.MATCH, f"{title}: {why}")
        self.assertEqual(sports.classify("Boxing: Usyk - Dubois", "", SPORT_CH).kind, sports.MATCH)

    def test_by_sound(self):
        self.assertEqual(sports.greek_latin("Ντόρτμουντ"), "dortmount")          # word-initial ντ is d, inside nt
        self.assertEqual(sports.greek_latin("Γιουβέντους"), "iouventous")
        for side, key in (("Ουντινέζε", "team:udinese"), ("Λεβερκούζεν", "team:bayer-leverkusen"), ("Μπεσίκτας", "team:besiktas"),
                          ("Ναϊμέγκεν", "team:nec-nijmegen"), ("Αλβέρκα", "team:alverca"), ("Κροατία", "team:croatia")):
            self.assertEqual(sports.greek_side(sports.norm(side).split()), sports.BY_ID_KEY[key].id, side)

    def test_no_guessing(self):
        for side in ("Στιγμιότυπα", "Ρεάλ", "Ουλμ"):                       # "highlights", too short, unknown
            self.assertEqual(sports.resolve_side(side)[0], -1, side)

    def test_new_spellings(self):
        for side, key in (("Olympique Marseille", "team:marseille"), ("Olympiakos Piraeus", "team:olympiacos"),
                          ("Sund'land", "team:sunderland"), ("Real Madryt", "team:real-madrid"), ("St Gilloisse", "team:union-saint-gilloise"),
                          ("Köln", "team:1-fc-koln"), ("Fortuna Köln", "team:fortuna-koln")):
            self.assertEqual(sports.resolve_side(side)[1], key, side)
        self.assertEqual(sports.resolve_side("Kiel")[0], -1, "THW Kiel plays handball: no football crest for a bare Kiel")

    def test_multi_sport_clubs(self):
        """EuroLeague clubs that are also football clubs count in basketball; other clubs don't."""
        b = sports.BY_KEY["basketball"]
        info = sports.classify("Basketball: Φενέρμπαχτσε vs Παρτίζαν", "", b)
        self.assertEqual(info.key, sports.classify("EuroLeague: Fenerbahce vs Partizan", "", b).key, "one card")
        self.assertEqual([sports.ENTITIES[t].key for t in info.teams], ["team:fenerbahce", "team:partizan"])
        self.assertNotEqual(sports.classify("Basketball: Spurs vs Arsenal", "", b).teams[1:], (sports.BY_ID_KEY["team:arsenal"].id,),
                            "Arsenal is not in basketball")

    def test_us_leagues_by_city_and_nickname_only_in_their_sport(self):
        """US guides name NBA/NFL teams by city or nickname ("Atlanta vs San Antonio", "A Falcons"). Those
        names count only when the event is that sport: in football, "Spurs" is still Tottenham."""
        key = lambda t, ch: [sports.ENTITIES[x].key if x >= 0 else None for x in sports.classify(t, "", ch).teams]
        b, n, f = sports.BY_KEY["basketball"], sports.BY_KEY["nfl"], sports.BY_KEY["football"]
        self.assertEqual(key("Atlanta vs San Antonio", b), ["team:atlanta-hawks", "team:san-antonio-spurs"])
        self.assertEqual(key("NBA: Spurs vs Lakers", 0), ["team:san-antonio-spurs", "team:los-angeles-lakers"])
        self.assertEqual(key("NFL: A Falcons vs C Bears", 0), ["team:atlanta-falcons", "team:chicago-bears"])
        self.assertEqual(key("Jaguars vs Eagles", n), ["team:jacksonville-jaguars", "team:philadelphia-eagles"])
        self.assertEqual(key("Spurs vs Arsenal", f), ["team:tottenham-hotspur", "team:arsenal"])
        self.assertEqual(key("Wolves vs Arsenal", f), ["team:wolverhampton-wanderers", "team:arsenal"])
        self.assertIsNone(sports.classify("Atlanta vs Houston", "", 0), "no sport, no guess")
        wnba = sports.classify("Golden State vs Las Vegas - Semi Final - Game 3 - Women's National Basketball", "", b)
        self.assertEqual(wnba.teams, (-1, -1), "a WNBA 'Golden State' is not the Warriors")
        self.assertEqual([sports.ENTITIES[e].key for _, _, e in sports.query_groups(["spurs"])], ["team:tottenham-hotspur"])


if __name__ == "__main__":
    unittest.main()
