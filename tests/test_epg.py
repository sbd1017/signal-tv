"""The guide: each channel reads one source, the right one."""
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tvapp import epg

H = 3600
NOW = int(time.time()) // H * H


def stamp(h):
    return datetime.fromtimestamp(NOW + h * H, timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def guide(programmes, live, cats=None, channels=()):
    xml = "<tv>" + "".join(f'<channel id="{c}"><display-name>{n}</display-name></channel>' for c, n in channels)
    xml += "".join(f'<programme channel="{c}" start="{stamp(a)}" stop="{stamp(b)}"><title>{t}</title></programme>'
                   for c, a, b, t in programmes) + "</tv>"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guide.xml"
        path.write_text(xml)
        return {i: [(round((r[0] - NOW) / H, 2), r[2]) for r in rows] for i, rows in epg.parse_xmltv(path, live, cats).items()}


def ch(iid, name, gid="", cat=""):
    return {"id": iid, "name": name, "epg": gid, "epg_name": name, "cat": cat}


class OneSource(unittest.TestCase):
    def test_sources_stacked_under_one_id_are_never_interleaved(self):
        """Two sources under beinsports2.qa, the second hours out: the channel seemed to show three games at once."""
        live = [ch("l_a", "AR: BEIN 2", "bein2.qa")]
        g = guide([("bein2.qa", -2, 0, "Sabah vs Barcelona"), ("bein2.qa", 0, 2, "Sporting vs Man Utd"), ("bein2.qa", 2, 4, "Melbourne"),
                   ("bein2.qa", -1, 1, "Leipzig vs Lens"), ("bein2.qa", 4, 6, "After it")], live)
        self.assertEqual(g["l_a"], [(-2, "Sabah vs Barcelona"), (0, "Sporting vs Man Utd"), (2, "Melbourne"), (4, "After it")])

    def test_a_source_that_starts_later_leaves_today_to_the_other(self):
        live = [ch("l_a", "AR: BEIN 2", "bein2.qa")]
        g = guide([("bein2.qa", 5, 6, "A"), ("bein2.qa", 6, 7, "B"), ("bein2.qa", 7, 8, "C"), ("bein2.qa", 0, 2, "Now")], live)
        self.assertEqual([t for _, t in g["l_a"]], ["Now", "A", "B", "C"])

    def test_capitals_are_different_guides(self):
        """beINSports2.qa is beinsports2.qa three hours out; the spelling most channels carry is right."""
        live = [ch("l_a", "AR: BEIN 2 HD", "bein2.qa"), ch("l_b", "AR: BEIN 2 SD", "bein2.qa"), ch("l_c", "AR: BEIN 2 RAW", "beIN2.qa")]
        g = guide([("beIN2.qa", 3, 5, "Shifted"), ("beIN2.qa", 5, 6, "More"), ("bein2.qa", 0, 2, "Right")], live)
        self.assertEqual({i: [t for _, t in r] for i, r in g.items()}, {"l_a": ["Right"], "l_b": ["Right"], "l_c": ["Right"]})

    def test_another_spelling_is_used_when_its_own_has_nothing(self):
        g = guide([("bein2.qa", 0, 2, "Right")], [ch("l_a", "AR: BEIN 2", "BEIN2.QA")])
        self.assertEqual(g, {"l_a": [(0, "Right")]})

    def test_a_channel_without_an_id_is_found_by_name(self):
        live = [ch("l_a", "Channel Four"), ch("l_b", "Other", "other.uk")]
        g = guide([("four.uk", 0, 2, "News"), ("other.uk", 0, 2, "Film")], live, channels=[("four.uk", "Channel Four"), ("other.uk", "Other")])
        self.assertEqual(g, {"l_a": [(0, "News")], "l_b": [(0, "Film")]})


class Links(unittest.TestCase):
    def test_versions_that_disagree_take_the_country_in_the_name(self):
        """beIN SPORTS 2 FRANCE: the RAW version carried Qatar's guide (Sporting v Manchester United) while
        the channel showed the EuroLeague, as its HD version's guide said."""
        cats = {"1": "AR| BEIN SPORTS", "2": "DE| SKY", "3": "UK| NEWS"}
        live = [ch("l_hd", "8K: beIN SPORTS 2 FRANCE ᴴᴰ", "BeinSports2.fr", "1"), ch("l_raw", "8K: beIN SPORTS 2 FRANCE ᴿᴬᵂ", "beINSports2.qa", "1"),
                ch("l_qa", "8K: beIN SPORTS 2 ᴿᴬᵂ", "beinsports2.qa", "1"),
                ch("l_f1", "SKYGO: SKY SPORT F1 4K", "SkySportsF1.uk", "2"), ch("l_f1hd", "SKYGO: SKY SPORT F1 HD", "SkySportF1.de", "2"),
                ch("l_n1", "UK: SOME NEWS HD", "somenews.us", "3"), ch("l_n2", "UK: SOME NEWS 4K", "somenews.qa", "3")]
        ids = epg.guide_ids(live, cats)
        self.assertEqual(ids["l_raw"], "BeinSports2.fr")
        self.assertEqual(ids["l_hd"], "BeinSports2.fr")
        self.assertEqual(ids["l_qa"], "beinsports2.qa", "the Qatari channel keeps its own")
        self.assertEqual(ids["l_f1"], "SkySportF1.de", "the category says Germany")
        self.assertEqual((ids["l_n1"], ids["l_n2"]), ("somenews.us", "somenews.qa"), "neither is the name's country: left alone")


if __name__ == "__main__":
    unittest.main()
