"""More like this (tvapp/similar.py): series by genre, shared description words and era; films by
their genre's categories and era; same language, one version per title."""
import unittest

from tvapp import similar


def series(id_, name, genre, year, plot="", rating=7):
    return {"id": id_, "name": name, "genre": genre, "year": year, "plot": plot, "rating": rating, "cat": "1"}


FILLER = [series(f"sx{i}", f"EN - Filler {i}", "Documentary", 2001, f"wildlife ocean penguins {i}") for i in range(40)]


class Labels(unittest.TestCase):
    def test_label_and_genres(self):
        self.assertEqual(similar.label("EN - Martin (1992) (US)"), ("EN", "martin"))
        self.assertEqual(similar.label("4K-DE-HDR - Dune (2021)"), ("DE", "dune"))
        self.assertEqual(similar.label("UK - Friends"), ("EN", "friends"))
        self.assertEqual(similar.label("Plain Title"), ("", "plain title"))
        self.assertEqual(similar.genres("Comedy / Drama"), {"comedy", "drama"})
        self.assertEqual(similar.genres("Sci-Fi & Fantasy"), {"science fiction", "fantasy"})
        self.assertEqual(similar.genres("EN - SCIENCE FICTION"), {"science fiction"})
        self.assertEqual(similar.genre_order("Action, Crime, Drama"), ["action", "crime", "drama"])


class Series(unittest.TestCase):
    def setUp(self):
        self.data = {"series": FILLER + [
            series("s1", "EN - Martin (1992) (US)", "Comedy / Drama", 1992, "A sitcom about a radio host in Detroit and his girlfriend."),
            series("s2", "EN - Living Single (US)", "Comedy", 1993, "A sitcom about friends sharing a Brooklyn brownstone."),
            series("s3", "EN - The Wire", "Crime / Drama", 2002, "Baltimore police and drug dealers."),
            series("s4", "EN - Frasier", "Comedy", 1993, "A radio psychiatrist and his family."),
            series("s5", "DE - Martin Show", "Comedy", 1992, "A sitcom about a radio host."),           # another language
            series("s6", "AR-SUBS - Martin (1992)", "Comedy / Drama", 1992, "Sitcom radio host."),      # another version
            series("s7", "EN - Living Single (1993)", "Comedy", 1993, "A sitcom about friends sharing a brownstone."),
            series("s8", "EN - Planet Earth", "Documentary", 2006, "Wildlife across the planet."),
        ]}
        self.like = similar.Similar()
        self.like.prepare(self.data, "v1")

    def test_same_language_one_version_per_title(self):
        ids = self.like.like_series("s1")
        self.assertIn("s4", ids)
        self.assertEqual(sum(i in ids for i in ("s2", "s7")), 1, "Living Single once")
        for other in ("s1", "s5", "s6", "s8"):
            self.assertNotIn(other, ids)
        self.assertLess(ids.index("s4"), ids.index("s3") if "s3" in ids else 99, "a 90s radio sitcom before a crime drama")

    def test_index_once_per_version(self):
        before = self.like.series
        self.like.prepare(self.data, "v1")
        self.assertIs(self.like.series, before)
        self.assertEqual(self.like.like_series("nope"), [])


class Films(unittest.TestCase):
    def test_by_first_genre_then_era(self):
        data = {"cats": {"movie": {"a": "EN - ACTION", "d": "EN - DRAMA", "n": "EN - NEW RELEASE", "x": "DE - ACTION"}}, "movie": [
            {"id": "m1", "name": "EN - The Dark Knight (2008)", "cat": "n", "year": 2008, "rating": 9},
            {"id": "m2", "name": "EN - Taken (2008)", "cat": "a", "year": 2008, "rating": 7},
            {"id": "m3", "name": "EN - Gran Torino (2008)", "cat": "d", "year": 2008, "rating": 8},
            {"id": "m4", "name": "EN - Rambo (1982)", "cat": "a", "year": 1982, "rating": 7},
            {"id": "m5", "name": "DE - Taken (2008)", "cat": "x", "year": 2008, "rating": 7},
            {"id": "m6", "name": "EN - The Dark Knight (2008)", "cat": "a", "year": 2008, "rating": 9},
        ]}
        ids = similar.Similar.like_film(data, data["movie"][0], "Action, Crime, Drama")
        self.assertEqual(ids[:3], ["m2", "m4", "m3"], "action first (closest year first), then drama")
        self.assertNotIn("m5", ids)
        self.assertNotIn("m6", ids, "another version of the same film")


if __name__ == "__main__":
    unittest.main()
