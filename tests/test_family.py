"""Family sites: one passphrase per site, set by the owner (also from the owner's own Settings), sessions
that end when it changes, and the site at its own address (tvapp/family.py)."""
import asyncio
import dataclasses
import os
import time
from unittest import mock
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tvapp import family, server
from tvapp.auth import COOKIE, Keys
from tests.test_state_api import WRITE, settings

PHRASE = "correct horse battery"
NGINX = {"X-Forwarded-For": "203.0.113.7"}             # every request from outside comes through nginx


class Record(unittest.TestCase):
    def test_hash_verify_and_generations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "family" / "mumtv.json"
            rec = family.set_passphrase(path, PHRASE)
            self.assertNotIn(PHRASE, path.read_text(), "only a hash is stored")
            self.assertTrue(family.verify(rec, PHRASE))
            self.assertFalse(family.verify(rec, PHRASE + "!"))
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            acc = family.Access(path)
            g1 = acc.gen()
            family.sign_out_all(path)
            self.assertEqual(acc.gen(), g1 + 1, "the file is re-read when it changes")
            family.set_passphrase(path, "another one")
            self.assertEqual(acc.gen(), g1 + 2)
            self.assertFalse(acc.verify(PHRASE))
            self.assertTrue(acc.verify("another one"))

    def test_rules(self):
        self.assertIsNotNone(family.check_passphrase("short"))
        self.assertIsNone(family.check_passphrase("long enough"))
        self.assertFalse(family.Access(None).is_set())

    def test_throttle(self):
        t = [1000.0]
        th = family.Throttle(clock=lambda: t[0])
        for _ in range(5):
            self.assertFalse(th.blocked("a"))
            th.failed("a")
        self.assertTrue(th.blocked("a"), "five wrong tries from one address")
        self.assertFalse(th.blocked("b"), "others still can")
        t[0] += 901
        self.assertFalse(th.blocked("a"), "after 15 minutes")

    def test_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "mumtv.site").write_text("TV_SITE=mumtv\nTV_BASE=/mumtv\nTV_PORT=8793\n")
            (d / "bad.site").write_text("TV_SITE=Bad Name\nTV_PORT=1\n")
            self.assertEqual(family.sites(d), [{"name": "mumtv", "base": "/mumtv", "port": 8793}])


class FamilySite(unittest.TestCase):
    """The app as a family site: TV_AUTH=passphrase at /mumtv."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.rec = d / "owner" / "family" / "mumtv.json"
        server.S.settings = dataclasses.replace(settings(d), base="/mumtv", auth="passphrase", site="mumtv",
                                                access_file=self.rec, classic=False)
        server.S.keys = Keys(d)
        server.S.access = family.Access(self.rec)
        server.S.throttle = family.Throttle()
        self.c = TestClient(server.app, follow_redirects=False)

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phrase, headers=None):
        return self.c.post("/tv/api/login", content=f"passphrase={phrase.replace(' ', '+')}",
                           headers={**NGINX, "Content-Type": "application/x-www-form-urlencoded", "Origin": "https://example.com", **(headers or {})})

    def test_not_set_up_yet(self):
        r = self.c.get("/tv/", headers=NGINX)
        self.assertEqual(r.status_code, 200)
        self.assertIn('action="/mumtv/api/login"', r.text)
        self.assertIn("isn’t ready yet", r.text)
        self.assertEqual(self.login(PHRASE).headers["location"], "/mumtv/?e=3")

    def test_signed_out_sees_only_the_passphrase_page(self):
        family.set_passphrase(self.rec, PHRASE)
        page = self.c.get("/tv/", headers=NGINX)
        self.assertIn('name="passphrase"', page.text)
        self.assertIn("/mumtv/pwa/new/login.css", page.text)
        self.assertNotIn("isn’t ready", page.text)
        self.assertEqual(self.c.get("/tv/api/live", headers=NGINX).status_code, 401)
        self.assertEqual(self.c.get("/tv/new/static/js/app.js", headers=NGINX).status_code, 401)
        self.assertEqual(self.c.get("/tv/api/auth-check", headers=NGINX).status_code, 401)
        self.assertEqual(self.c.get("/tv/api/family", headers=NGINX).status_code, 401, "owner-only endpoints never reachable")

    def test_wrong_then_right_passphrase(self):
        family.set_passphrase(self.rec, PHRASE)
        bad = self.login("nope nope")
        self.assertEqual((bad.status_code, bad.headers["location"]), (303, "/mumtv/?e=1"))
        self.assertNotIn(COOKIE, bad.cookies)
        good = self.login(PHRASE)
        self.assertEqual((good.status_code, good.headers["location"]), (303, "/mumtv/"))
        cookie = good.headers["set-cookie"]
        self.assertIn("Path=/mumtv/", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        value = good.cookies[COOKIE]
        self.assertEqual(self.c.get("/tv/api/auth-check", headers=NGINX, cookies={COOKIE: value}).status_code, 204)
        # the owner signs everyone out: this device's session ends
        family.sign_out_all(self.rec)
        self.assertEqual(self.c.get("/tv/api/auth-check", headers=NGINX, cookies={COOKIE: value}).status_code, 401)

    def test_the_owners_cookie_is_no_use_here(self):
        family.set_passphrase(self.rec, PHRASE)
        owner_style = server.S.keys.make_cookie()                # generation 0: the /tv kind
        self.assertEqual(self.c.get("/tv/api/auth-check", headers=NGINX, cookies={COOKIE: owner_style}).status_code, 401)

    def test_guessing_is_limited(self):
        family.set_passphrase(self.rec, PHRASE)
        for _ in range(5):
            self.login("wrong guess")
        self.assertEqual(self.login(PHRASE).headers["location"], "/mumtv/?e=2", "even the right one waits")

    def test_another_sites_form_cannot_sign_in(self):
        family.set_passphrase(self.rec, PHRASE)
        self.assertEqual(self.login(PHRASE, {"Origin": "https://evil.example"}).status_code, 403)
        # our own form, with the site's no-referrer policy: the browser says Origin: null
        self.assertEqual(self.login(PHRASE, {"Origin": "null"}).headers["location"], "/mumtv/")

    def test_loopback_is_the_sidecar_and_iptv(self):
        family.set_passphrase(self.rec, PHRASE)
        local = TestClient(server.app, client=("127.0.0.1", 50000))
        self.assertNotEqual(local.get("/tv/api/auth-check").status_code, 500)
        self.assertEqual(TestClient(server.app, client=("127.0.0.1", 50000)).get("/tv/api/live", headers=NGINX).status_code, 401,
                         "through nginx (X-Forwarded-For) is never loopback")


class OwnersPanel(unittest.TestCase):
    """The owner's own site: Settings > Family sites."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "fam").mkdir()
        (d / "fam" / "mumtv.site").write_text("TV_SITE=mumtv\nTV_BASE=/mumtv\nTV_PORT=1\n".replace("TV_PORT=1", "TV_PORT=59999"))
        server.S.settings = dataclasses.replace(settings(d), family_dir=d / "fam")
        import httpx
        server.S.http = httpx.AsyncClient()
        self.c = TestClient(server.app)
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_passphrase_and_sign_out(self):
        r = self.c.get("/tv/api/family")
        self.assertEqual(r.status_code, 200)
        site = r.json()["sites"][0]
        self.assertEqual((site["name"], site["base"], site["passphrase"], site["up"]), ("mumtv", "/mumtv", False, False))
        self.assertEqual(self.c.post("/tv/api/family/mumtv/passphrase", content=json.dumps({"passphrase": "short"}), headers=WRITE).status_code, 400)
        self.assertEqual(self.c.post("/tv/api/family/mumtv/passphrase", content=json.dumps({"passphrase": PHRASE}),
                                     headers={"Content-Type": "application/json"}).status_code, 403, "our page's header only")
        self.assertEqual(self.c.post("/tv/api/family/joseph/passphrase", content=json.dumps({"passphrase": PHRASE}), headers=WRITE).status_code, 404)
        ok = self.c.post("/tv/api/family/mumtv/passphrase", content=json.dumps({"passphrase": PHRASE}), headers=WRITE)
        self.assertEqual(ok.status_code, 200)
        rec = family.read_record(self.d / "family" / "mumtv.json")
        self.assertTrue(family.verify(rec, PHRASE))
        gen = rec["gen"]
        self.assertEqual(self.c.post("/tv/api/family/mumtv/signout", headers=WRITE).status_code, 200)
        self.assertEqual(family.read_record(self.d / "family" / "mumtv.json")["gen"], gen + 1)
        self.assertTrue(self.c.get("/tv/api/family").json()["sites"][0]["passphrase"])


class Provider(unittest.TestCase):
    """The owner sets a family site's provider from Settings: read, checked with the provider, kept."""

    def test_form(self):
        v, why = family.parse_provider({"type": "xtream", "base": "line.example.com:8080/", "username": "u", "password": "p"})
        self.assertEqual(v, {"IPTV_PROVIDER_TYPE": "xtream", "XTREAM_BASE_URL": "http://line.example.com:8080", "XTREAM_USERNAME": "u",
                             "XTREAM_PASSWORD": "p"})
        v, _ = family.parse_provider({"type": "m3u", "url": "http://line.example.com:8080/get.php?username=u&password=p&type=m3u_plus"})
        self.assertEqual(v["IPTV_PROVIDER_TYPE"], "xtream", "an Xtream link is kept as the account it is")
        self.assertEqual((v["XTREAM_BASE_URL"], v["XTREAM_USERNAME"]), ("http://line.example.com:8080", "u"))
        v, _ = family.parse_provider({"type": "m3u", "url": "https://cdn.example.com/list.m3u8"})
        self.assertEqual(v, {"IPTV_PROVIDER_TYPE": "m3u", "IPTV_M3U_URL": "https://cdn.example.com/list.m3u8"})
        for bad in ({"type": "xtream", "base": "x", "username": "", "password": "p"}, {"type": "m3u", "url": "ftp://x"},
                    {"type": "xtream", "base": "http://a.b", "username": "u\nX=1", "password": "p"}, {"type": "other"}):
            self.assertIsNone(family.parse_provider(bad)[0], bad)

    def check(self, handler, values):
        import httpx
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
                return await family.check_provider(c, values, "ua")
        return asyncio.run(go())

    def test_check_says_what_is_wrong(self):
        import httpx
        x = {"IPTV_PROVIDER_TYPE": "xtream", "XTREAM_BASE_URL": "http://line.example.com:8080", "XTREAM_USERNAME": "u", "XTREAM_PASSWORD": "p"}
        ok = self.check(lambda r: httpx.Response(200, json={"user_info": {"auth": 1, "status": "Active", "exp_date": "1800000000"}}), x)
        self.assertEqual((ok[0], ok[1]["expires"]), ("", 1800000000))
        self.assertIn("doesn't recognise that address",
                      self.check(lambda r: httpx.Response(400, json={"error": "Unrecognised server hostname."}), x)[0])
        self.assertIn("refused", self.check(lambda r: httpx.Response(200, json={"user_info": {"auth": 0}}), x)[0])
        self.assertIn("expired", self.check(lambda r: httpx.Response(200, json={"user_info": {"auth": 1, "status": "Expired"}}), x)[0])
        def refuse(r):
            raise httpx.ConnectError("refused")
        self.assertIn("line.example.com:8080", self.check(refuse, x)[0])
        m = {"IPTV_PROVIDER_TYPE": "m3u", "IPTV_M3U_URL": "http://cdn.example.com/a.m3u"}
        self.assertEqual(self.check(lambda r: httpx.Response(200, content=b"#EXTM3U\n#EXTINF:-1,A\nhttp://x/1.ts\n"), m)[0], "")
        self.assertIn("didn't return a playlist", self.check(lambda r: httpx.Response(200, content=b"<html>"), m)[0])

    def test_saved_last_wins(self):
        from tvapp import config as cfg
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            env = d / "mumtv.env"
            env.write_text("IPTV_PROVIDER_TYPE=xtream\nXTREAM_BASE_URL=http://old.example.com\nXTREAM_USERNAME=a\nXTREAM_PASSWORD=b\n")
            with mock.patch.object(cfg, "CONFIG_PATH", env), \
                    mock.patch.dict(os.environ, {"STATE_DIRECTORY": str(d / "state"), "TV_AUTH": "passphrase"}):
                self.assertEqual(cfg.load().provider_source, "file")
                p = family.write_provider(d / "state", {"IPTV_PROVIDER_TYPE": "m3u", "IPTV_M3U_URL": "http://new.example.com/l.m3u"})
                self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
                os.utime(env, (time.time() - 60, time.time() - 60))
                s = cfg.load()
                self.assertEqual((s.provider_source, s.provider_type, s.m3u_url), ("web", "m3u", "http://new.example.com/l.m3u"))
                os.utime(env, None)                                   # `iptv family mumtv set-xtream` afterwards
                os.utime(p, (time.time() - 60, time.time() - 60))
                self.assertEqual((cfg.load().provider_source, cfg.load().xtream_base), ("file", "http://old.example.com"))
                with mock.patch.dict(os.environ, {"TV_AUTH": ""}):
                    os.utime(p, None)
                    self.assertEqual(cfg.load().provider_source, "file", "the owner's own site never reads it")

    def test_internal_endpoint_is_loopback_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            server.S.settings = dataclasses.replace(settings(d), base="/mumtv", auth="passphrase", site="mumtv",
                                                    access_file=d / "rec.json", classic=False)
            server.S.keys = Keys(d)
            server.S.access = family.Access(d / "rec.json")
            server.S.throttle = family.Throttle()
            outside = TestClient(server.app)
            self.assertIn(outside.get("/tv/api/internal/provider", headers=NGINX).status_code, (401, 404))
            self.assertIn(outside.post("/tv/api/internal/provider", json={"type": "m3u", "url": "http://x/a.m3u"}, headers=NGINX).status_code, (401, 404))
            local = TestClient(server.app, client=("127.0.0.1", 50000))
            r = local.get("/tv/api/internal/provider")
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("password", r.text.lower())
            self.assertEqual(local.post("/tv/api/internal/provider", json={"type": "xtream", "base": "", "username": "", "password": ""}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
