"""Family sites: one passphrase per site, set by the owner (also from the owner's own Settings), sessions
that end when it changes, and the site at its own address (tvapp/family.py)."""
import dataclasses
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


if __name__ == "__main__":
    unittest.main()
