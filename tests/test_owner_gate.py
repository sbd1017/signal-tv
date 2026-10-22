"""The owner's copy behind the central login (SITE_AUTH=1) checks that login itself.

nginx's identity headers count only from loopback and with this app's proxy key (tvapp/site_auth.py);
programs on the Pi calling directly use the internal key (tvapp/internalkey.py). A loopback address alone,
with or without X-Forwarded-For, proves nothing. The artwork sidecar applies the same rules.
"""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from tvapp import server
from tvapp.userstate import StateStore
from tests.test_state_api import settings

PKEY, IKEY = "p" * 64, "i" * 64
OWNER = {"X-Site-User": "owner", "X-Site-CSRF": "c" * 43, "X-Site-Expires": str(int(time.time()) + 3600),
         "X-Site-Proxy-Key": PKEY}


class Keys(unittest.TestCase):
    """Both key files, as systemd would hand them over."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "proxy").write_text(PKEY + "\n")
        (d / "internal").write_text(IKEY + "\n")
        env = mock.patch.dict(os.environ, {"SITE_AUTH": "1", "SITE_PROXY_KEY_FILE": str(d / "proxy"),
                                           "TV_INTERNAL_KEY_FILE": str(d / "internal")})
        env.start()
        self.addCleanup(env.stop)                   # even if a subclass's setUp fails: never leak SITE_AUTH=1
        self.addCleanup(self.tmp.cleanup)


class OwnerGate(Keys):
    def setUp(self):
        super().setUp()
        server.S.settings = settings(Path(self.tmp.name))          # auth="nginx": the owner's copy
        server.S.state = StateStore(Path(self.tmp.name) / "state.db")

    def tearDown(self):
        server.S.state.close()

    def get(self, path, headers=None, peer="127.0.0.1"):
        return TestClient(server.app, client=(peer, 50000)).get(path, headers=headers or {})

    def test_signed_in_owner_through_nginx(self):
        self.assertEqual(self.get("/tv/api/state", OWNER).status_code, 200)

    def test_forged_identity_without_the_proxy_key(self):
        no_key = {k: v for k, v in OWNER.items() if k != "X-Site-Proxy-Key"}
        for headers in (no_key, {**no_key, "X-Forwarded-For": "203.0.113.9"}, {**OWNER, "X-Site-Proxy-Key": "p" * 63 + "x"},
                        {**OWNER, "X-Site-User": "mum"}, {**OWNER, "X-Site-Expires": "1"}, {}):
            self.assertEqual(self.get("/tv/api/state", headers).status_code, 401, headers)
        self.assertEqual(self.get("/tv/", no_key).status_code, 401)

    def test_programs_on_the_pi_with_the_internal_key(self):
        key = {"X-TV-Internal-Key": IKEY}
        self.assertEqual(self.get("/tv/api/state", key).status_code, 200)              # the sidecar, iptv, devproxy
        self.assertEqual(self.get("/tv/api/state", {"X-TV-Internal-Key": "i" * 63 + "x"}).status_code, 401)
        self.assertEqual(self.get("/tv/api/state", key, peer="203.0.113.9").status_code, 401, "loopback only")

    def test_keys_count_only_on_loopback(self):
        self.assertEqual(self.get("/tv/api/state", OWNER, peer="203.0.113.9").status_code, 401)

    def test_media_and_install_files_stay_open(self):
        self.assertNotEqual(self.get("/tv/m/not-a-token/x.ts").status_code, 401)
        self.assertNotEqual(self.get("/tv/pwa/manifest.webmanifest").status_code, 401)

    def test_off_without_site_auth(self):
        with mock.patch.dict(os.environ, {"SITE_AUTH": ""}):
            self.assertEqual(self.get("/tv/api/state").status_code, 200)      # local preview / isolated stack

    def test_refuses_to_start_without_the_proxy_key(self):
        async def start():
            async with server.lifespan(server.app):
                pass
        with mock.patch.dict(os.environ, {"SITE_PROXY_KEY_FILE": "/nonexistent"}), \
                mock.patch.object(server.cfg, "load", return_value=settings(Path(self.tmp.name))):
            with self.assertRaisesRegex(SystemExit, "proxy key"):
                asyncio.run(start())


try:
    import PIL  # noqa: F401
except ImportError:
    PIL = None


@unittest.skipIf(PIL is None, "tvnext needs Pillow: run with /opt/signal-tv-next/venv/bin/python")
class Sidecar(Keys):
    def setUp(self):
        super().setUp()
        os.environ.setdefault("TVN_STATE", tempfile.mkdtemp())
        os.environ.setdefault("TVN_CACHE", tempfile.mkdtemp())
        from tvnext import config, server as tvn
        self.tvn = tvn
        site_auth = mock.patch.object(config, "SITE_AUTH", True)
        site_auth.start()
        self.addCleanup(site_auth.stop)

    def post(self, path, headers=None, peer="127.0.0.1", **kw):
        return TestClient(self.tvn.app, client=(peer, 50000)).post(path, headers=headers or {}, **kw)

    def test_internal_routes_need_the_internal_key(self):
        bad = {"content": b"not json", "headers": {"Content-Type": "application/json"}}
        self.assertEqual(self.post("/internal/tmdb-key", bad["headers"], content=bad["content"]).status_code, 404,
                         "loopback alone proves nothing")
        self.assertEqual(self.post("/internal/tmdb-key", {**bad["headers"], "X-TV-Internal-Key": IKEY},
                                   content=bad["content"]).status_code, 400, "reaches the handler")
        self.assertEqual(self.post("/internal/tmdb-key", {**bad["headers"], "X-TV-Internal-Key": IKEY},
                                   peer="203.0.113.9", content=bad["content"]).status_code, 404)

    def test_adding_a_crest_needs_the_owner(self):
        path = "/tv/next/api/art/manual?id=team:1&sport=football"
        text = {"Content-Type": "text/plain"}
        self.assertEqual(self.post(path, text, content=b"x").status_code, 401)
        no_key = {k: v for k, v in OWNER.items() if k != "X-Site-Proxy-Key"}
        self.assertEqual(self.post(path, {**text, **no_key}, content=b"x").status_code, 401)
        r = self.post(path, {**text, **OWNER}, content=b"x")
        self.assertEqual((r.status_code, r.json().get("error")), (400, "Send an image."), "the owner gets past the check")


if __name__ == "__main__":
    unittest.main()
