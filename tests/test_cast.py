"""Cast in the player (tvnext/cast.py): the owner's TMDB key, film and episode credits (guest stars
too), a title found by exact name when the provider gives no TMDB number, answers kept on disk."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import httpx

os.environ.setdefault("TVN_STATE", tempfile.mkdtemp())
os.environ.setdefault("TVN_CACHE", tempfile.mkdtemp())

from tvnext import cast  # noqa: E402

KEY = "0123456789abcdef0123456789abcdef"


def person(name, character, photo="/abcdefgh123.jpg"):
    return {"name": name, "character": character, "profile_path": photo}


class FakeTMDB:
    def __init__(self):
        self.calls = []

    def __call__(self, request):
        path, q = request.url.path, dict(request.url.params)
        self.calls.append(path)
        if q.get("api_key") != KEY:
            return httpx.Response(401, json={"status_message": "Invalid API key"})
        if path == "/3/configuration":
            return httpx.Response(200, json={"images": {}})
        if path == "/3/movie/155/credits":
            return httpx.Response(200, json={"cast": [person("Christian Bale", "Bruce Wayne"), person("Heath Ledger", "Joker", None)]})
        if path == "/3/tv/171/season/1/episode/3/credits":
            return httpx.Response(200, json={"cast": [person("Martin Lawrence", "Martin Payne")],
                                             "guest_stars": [person("Guest Person", "Officer")]})
        if path == "/3/search/movie":
            return httpx.Response(200, json={"results": [{"id": 9, "title": "Dune", "release_date": "2021-09-15"},
                                                         {"id": 8, "title": "Dune", "release_date": "1984-12-14"}]})
        if path == "/3/movie/9/credits":
            return httpx.Response(200, json={"cast": [person("Timothée Chalamet", "Paul Atreides")]})
        return httpx.Response(404, json={})


class Cast(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.tmdb = FakeTMDB()
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.tmdb))
        self.c = cast.Cast(self.client, d / "state", d / "cache")

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.tmp.cleanup()

    def run_(self, coro):
        return asyncio.run(coro)

    def test_key_kinds_check_and_storage(self):
        self.assertEqual(cast.key_kind(KEY), "v3")
        self.assertEqual(cast.key_kind("eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ4In0.c2lnbmF0dXJl"), "v4")
        self.assertIsNone(cast.key_kind("hello"))
        self.assertIn("doesn't look like", self.run_(self.c.check_key("hello")))
        self.assertIn("refused", self.run_(self.c.check_key("f" * 32)))
        self.assertEqual(self.run_(self.c.check_key(KEY)), "")
        self.assertFalse(self.c.status()["on"])
        self.c.save_key(KEY)
        self.assertEqual(oct((self.c.keyfile).stat().st_mode & 0o777), "0o600")
        self.assertTrue(self.c.status()["on"])
        self.assertNotIn(KEY, json.dumps(self.c.status()), "the key itself is never shown")
        self.c.save_key("")
        self.assertFalse(self.c.status()["on"])

    def test_off_without_a_key(self):
        self.assertEqual(self.run_(self.c.lookup("movie", 155, "The Dark Knight", 2008, 0, 0))["reason"], "off")

    def test_film_episode_and_cache(self):
        self.c.save_key(KEY)
        film = self.run_(self.c.lookup("movie", 155, "The Dark Knight", 2008, 0, 0))
        self.assertEqual([(p["name"], p["character"], bool(p["photo"])) for p in film["cast"]],
                         [("Christian Bale", "Bruce Wayne", True), ("Heath Ledger", "Joker", False)])
        ep = self.run_(self.c.lookup("tv", 171, "Martin", 1992, 1, 3))
        self.assertEqual([(p["name"], p["guest"]) for p in ep["cast"]], [("Martin Lawrence", False), ("Guest Person", True)])
        n = len(self.tmdb.calls)
        self.run_(self.c.lookup("movie", 155, "The Dark Knight", 2008, 0, 0))
        self.assertEqual(len(self.tmdb.calls), n, "the second time comes from disk")

    def test_found_by_exact_title_and_year_only(self):
        self.c.save_key(KEY)
        self.assertEqual(self.run_(self.c.lookup("movie", 0, "Dune", 2021, 0, 0))["cast"][0]["name"], "Timothée Chalamet")
        self.assertIsNone(self.run_(self.c.lookup("movie", 0, "Dune", 0, 0, 0))["cast"], "two Dunes and no year: nothing")

    def test_photos_only_from_tmdb_names(self):
        self.assertIsNone(self.run_(self.c.photo("w185", "../etc/passwd")))
        self.assertIsNone(self.run_(self.c.photo("original", "abcdefgh123.jpg")))


class KeyEndpoint(unittest.TestCase):
    def test_loopback_only(self):
        from fastapi.testclient import TestClient
        from tvnext import server
        with TestClient(server.app, client=("203.0.113.5", 1234)) as outside:
            self.assertEqual(outside.post("/internal/tmdb-key", json={"key": KEY}).status_code, 404)
            self.assertEqual(outside.get("/tv/next/api/cast/status").json()["on"], False)


if __name__ == "__main__":
    unittest.main()
