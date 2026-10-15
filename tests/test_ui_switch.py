"""deploy/ui-switch.sh build / use / status in a temporary tree (setup touches nginx and is not run
here; it backs both files up, refuses a snippet edited on the Pi, and restores them if nginx -t fails)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "ui-switch.sh"


class UiSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.ui = self.tmp / "ui"
        self.env = {**os.environ, "TV_UI_DIR": str(self.ui), "TV_APP_DIR": str(ROOT), "TV_SUDO": ""}

    def run_(self, *args, ok=True):
        r = subprocess.run(["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_build_keeps_the_default_and_use_sets_it(self):
        self.run_("build")
        self.assertEqual(os.readlink(self.ui / "default"), "classic", "a first build changes nothing for anyone")
        self.assertEqual(Path(os.readlink(self.ui / "classic")), ROOT / "web")
        self.assertTrue((self.ui / "new" / "index.html").is_file())
        self.run_("use", "new")
        self.assertEqual(os.readlink(self.ui / "default"), "new")
        self.run_("build")
        self.assertEqual(os.readlink(self.ui / "default"), "new", "a deploy keeps the default")
        self.assertIn("default:        new", self.run_("status").stdout)
        self.run_("use", "old")
        self.assertEqual(os.readlink(self.ui / "default"), "classic", "'old' is classic")
        self.assertFalse((self.ui / "default.tmp").exists())

    def test_old_builds_are_cleaned_but_the_previous_kept(self):
        self.run_("build")
        first = os.readlink(self.ui / "new")
        stale = self.ui / "new-0000000000"
        stale.mkdir()
        (self.ui / "new").unlink()
        os.symlink("new-1111111111", self.ui / "new")             # pretend an earlier build was in use
        (self.ui / "new-1111111111").mkdir()
        self.run_("build")
        left = sorted(p.name for p in self.ui.glob("new-*"))
        self.assertEqual(left, sorted({first, "new-1111111111"}), "this build and the one before it")

    def test_bad_arguments(self):
        self.assertEqual(self.run_("use", "sideways", ok=False).returncode, 2)
        self.assertEqual(self.run_("frobnicate", ok=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
