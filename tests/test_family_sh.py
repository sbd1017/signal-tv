"""deploy/family.sh, run for real against a temporary /etc, nginx and systemd (nothing on this machine changes)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "family.sh"
MAP_LINE = '    "~^POST:/tv/api/state(/import)?$" 1;\n'


class FamilySh(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.t)
        for d in ("fam", "ui", "snippets", "sites", "units", "backups"):
            (self.t / d).mkdir()
        shutil.copy(ROOT / "deploy" / "signal-tv.conf", self.t / "snippets" / "signal-tv.conf")
        (self.t / "site.conf").write_text("map $request_method:$uri $allowed {\n" + MAP_LINE + "}\n")
        self.env = {**os.environ, "TV_FAMILY_DIR": str(self.t / "fam"), "TV_APP_DIR": str(ROOT), "TV_UI_ROOT": str(self.t / "ui"),
                    "TV_SUDO": "", "TV_NGINX_SNIPPETS": str(self.t / "snippets"), "TV_UI_SITEMAP": str(self.t / "site.conf"),
                    "TV_SYSTEMCTL": "true", "TV_NGINX": "true", "TV_NGINX_SITES": str(self.t / "sites"), "TV_UNIT_DIR": str(self.t / "units"),
                    "TV_BACKUP_DIR": str(self.t / "backups"), "TV_ENV_OWNER": ""}

    def run_sh(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True)

    def test_add_two_sites(self):
        r = self.run_sh("add", "mumtv")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("family site mumtv", r.stdout)
        self.assertEqual((self.t / "fam" / "mumtv.site").read_text(), "TV_SITE=mumtv\nTV_BASE=/mumtv\nTV_PORT=8793\n")
        self.assertEqual(oct((self.t / "fam" / "mumtv.env").stat().st_mode & 0o777), "0o640", "the provider file is private")
        snip = (self.t / "snippets" / "signal-tv-family-mumtv.conf").read_text()
        self.assertIn("location ^~ /mumtv/ {", snip)
        self.assertIn("proxy_pass http://127.0.0.1:8793/tv/;", snip)
        self.assertNotIn("@NAME@", snip + "@PORT@")
        self.assertNotIn("basic-auth", snip, "the app's own passphrase page, no browser pop-up")
        self.assertIn("include snippets/signal-tv-family-*.conf;", (self.t / "snippets" / "signal-tv.conf").read_text())
        site = (self.t / "site.conf").read_text()
        self.assertIn("POST:/mumtv/(api/(state(/import)?|login|logout)|next/api/art/gaps)$", site)
        self.assertIn("POST:/tv/api/family/", site)
        ui = self.t / "ui" / "signal-tv-ui-mumtv"
        self.assertTrue((ui / "new" / "index.html").is_file())
        self.assertEqual(os.readlink(ui / "default"), "new")
        self.assertTrue((self.t / "units" / "signal-tv-family@.service").is_file())
        # a second one gets the next port; the owner's map line isn't repeated
        self.assertEqual(self.run_sh("add", "josephtv").returncode, 0)
        self.assertIn("TV_PORT=8794", (self.t / "fam" / "josephtv.site").read_text())
        self.assertEqual((self.t / "site.conf").read_text().count("POST:/tv/api/family/"), 1)
        out = self.run_sh("list").stdout
        self.assertIn("mumtv", out)
        self.assertIn("josephtv", out)

    def test_refusals(self):
        self.assertNotEqual(self.run_sh("add", "Mum TV").returncode, 0)
        self.assertNotEqual(self.run_sh("add", "tv-test").returncode, 0, "reserved")
        (self.t / "sites" / "site.conf").write_text("location /photos/ { }\n")
        self.assertIn("already used", self.run_sh("add", "photos").stdout)
        self.assertEqual(self.run_sh("add", "mumtv").returncode, 0)
        self.assertIn("exists already", self.run_sh("add", "mumtv").stdout)


if __name__ == "__main__":
    unittest.main()
