"""The new interface built for /tv (deploy/build_ui.py) and served by the app through the
/opt/signal-tv-ui/current symlink (deploy/ui-switch.sh)."""
import dataclasses
import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from deploy import build_ui
from tests.test_state_api import settings
from tvapp import server

ROOT = Path(__file__).resolve().parent.parent


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def text(self, out, rel):
        return (out / rel).read_text(encoding="utf-8")

    def test_tv_build_sits_beside_the_classic_interface(self):
        out = self.tmp / "new"
        v = build_ui.build("/tv", out)
        self.assertRegex(v, r"^[0-9a-f]{10}$")
        for f in [p for p in out.rglob("*") if p.is_file() and p.suffix in build_ui.TEXT]:
            t = f.read_text(encoding="utf-8")
            self.assertNotIn("/tv-test", t, f)
            self.assertNotIn("__V__", t, f)
        api_js = self.text(out, "static/js/api.js")
        self.assertIn("export const NEXT = '/tv/next';", api_js)
        self.assertIn("export const STATIC = '/tv/new/static';", api_js)
        index = self.text(out, "index.html")
        self.assertIn(f'href="/tv/new/static/app.css?v={v}"', index)
        self.assertIn('href="/tv/pwa/new/manifest.webmanifest', index, "its own manifest and icons, not Classic's")
        self.assertNotRegex(index, r'"/tv/pwa/(?!new/)', "nothing from Classic's home-screen files")
        m = json.loads(self.text(out, "pwa/manifest.webmanifest"))
        self.assertEqual((m["id"], m["scope"], m["name"]), ("/tv/", "/tv/", "TV"), "the same installed app as Classic's")
        self.assertTrue(all(i["src"].startswith("/tv/pwa/new/") for i in m["icons"]))
        self.assertIn('name="apple-mobile-web-app-title" content="TV"', index)
        self.assertFalse((out / "static/vendor").exists(), "hls.js is the classic interface's copy")
        hls = hashlib.sha256((ROOT / "web/static/vendor/hls.min.js").read_bytes()).hexdigest()[:10]
        self.assertIn(f"/tv/static/vendor/hls.min.js?v={hls}", self.text(out, "static/js/player.js"),
                      "versioned by its own content, not the new build's")
        self.assertFalse((out / "dev").exists(), "development pages stay out")

    def test_preview_build_is_the_source_stamped(self):
        out = self.tmp / "test"
        v = build_ui.build("/tv-test", out)
        self.assertIn("export const NEXT = '/tv-test';", self.text(out, "static/js/api.js"))
        self.assertIn(f"/tv-test/static/app.css?v={v}", self.text(out, "index.html"))
        self.assertFalse((out / "static/vendor").exists(), "the preview borrows /tv's hls.js")

    def test_refuses_leftovers_and_missing_files(self):
        src = self.tmp / "src"
        shutil.copytree(ROOT / "web-next", src, ignore=shutil.ignore_patterns("dev"))
        js = src / "static/js/app.js"
        js.write_text(js.read_text() + "\nconst STRAY = '/tv-test';\n")      # a base the rewrite rules don't know
        with self.assertRaises(SystemExit) as e:
            build_ui.build("/tv", self.tmp / "out1", src=src)
        self.assertIn("/tv-test left", str(e.exception))
        self.assertFalse((self.tmp / "out1").exists(), "nothing half-built is left behind")
        shutil.rmtree(src)
        shutil.copytree(ROOT / "web-next", src, ignore=shutil.ignore_patterns("dev"))
        (src / "static/app.css").unlink()
        with self.assertRaises(SystemExit) as e:
            build_ui.build("/tv", self.tmp / "out2", src=src)
        self.assertIn("app.css: not found", str(e.exception))

    def test_same_source_same_version(self):
        self.assertEqual(build_ui.build("/tv", self.tmp / "a"), build_ui.build("/tv", self.tmp / "b"))


class Served(unittest.TestCase):
    """The app offering both interfaces: each device's choice (tv_ui cookie), else the Pi's default."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        classic = self.tmp / "web"
        (classic / "static" / "vendor").mkdir(parents=True)
        (classic / "pwa").mkdir()
        (classic / "index.html").write_text("<!doctype html><title>classic</title>")
        (classic / "static" / "vendor" / "hls.min.js").write_text("// hls")
        (classic / "static" / "app.css").write_text("/* classic */")
        (classic / "pwa" / "manifest.webmanifest").write_text('{"scope": "/tv/"}')
        ui = self.tmp / "ui"
        ui.mkdir()
        self.v = build_ui.build("/tv", ui / "new-x")
        os.symlink("new-x", ui / "new")
        os.symlink("classic", ui / "default")
        self.ui = ui
        server.S.settings = dataclasses.replace(settings(self.tmp), web_dir=classic, ui_dir=ui)
        self.c = TestClient(server.app)

    def page(self, cookie=None):
        self.c.cookies.clear()
        if cookie:
            self.c.cookies.set("tv_ui", cookie, path="/tv/")
        return self.c.get("/tv/").text

    def test_each_device_chooses(self):
        self.assertIn("<title>classic</title>", self.page(), "no choice: the Pi's default")
        self.assertIn("/tv/new/static/js/app.js", self.page("new"))
        self.assertIn("<title>classic</title>", self.page("classic"))
        self.assertIn("<title>classic</title>", self.page("sideways"), "anything else: the default")

    def test_the_pis_default_and_a_missing_build(self):
        os.replace(self._link("new"), self.ui / "default")
        self.assertIn("/tv/new/static/js/app.js", self.page())
        self.assertIn("<title>classic</title>", self.page("classic"), "a device's own choice wins")
        (self.ui / "new").unlink()
        self.assertIn("<title>classic</title>", self.page("new"), "no new build: never a broken page")
        self.assertIn("<title>classic</title>", self.page())

    def _link(self, target):
        tmp = self.ui / "default.tmp"
        os.symlink(target, tmp)
        return tmp

    def test_each_interface_keeps_its_own_files(self):
        font = next((self.ui / "new" / "static" / "fonts").glob("*.woff2")).name
        r = self.c.get(f"/tv/new/static/fonts/{font}", params={"v": self.v})
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "font/woff2"))
        self.assertEqual(self.c.get("/tv/new/static/js/app.js").status_code, 200)
        self.assertEqual(self.c.get("/tv/static/app.css").text, "/* classic */")
        self.assertEqual(self.c.get("/tv/static/vendor/hls.min.js").status_code, 200)
        self.assertEqual(self.c.get("/tv/new/pwa/manifest.webmanifest").status_code, 404, "only static/ under /tv/new")
        r = self.c.get("/tv/pwa/new/manifest.webmanifest")
        self.assertEqual((r.status_code, r.json()["scope"]), (200, "/tv/"), "the new interface's own manifest")
        self.assertEqual(self.c.get("/tv/pwa/new/icon.svg").headers["content-type"], "image/svg+xml")
        self.assertEqual(self.c.get("/tv/pwa/manifest.webmanifest").json(), {"scope": "/tv/"}, "Classic's own, untouched")
        for path in ("/tv/new/static/../index.html", "/tv/new/static/%2e%2e/index.html", "/tv/other/x.js", "/tv/new/x.js"):
            self.assertEqual(self.c.get(path).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
