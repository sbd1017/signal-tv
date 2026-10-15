#!/usr/bin/env python3
"""Build the web-next interface for where it will be served.

    build_ui.py --base /tv-test OUT     the preview (static files from nginx, as today)
    build_ui.py --base /tv      OUT     the live app, beside the classic interface: its own files under
                                        /tv/new/static (served by signal-tv from <ui_dir>/new), the
                                        sidecar under /tv/next/ (behind /tv's own login)
    build_ui.py --base /mumtv   OUT     a family site (tvapp/family.py): as /tv, at its own address -
                                        its API, files, video player and sidecar all under /mumtv/

The source (web-next/) is written for /tv-test. For /tv the build rewrites, in this order:
    NEXT = '/tv-test'  (api.js: the sidecar)   -> '/tv/next'
    /tv-test/static -> /tv/new/static,   /tv-test/pwa -> /tv/pwa/new,   any other /tv-test/ -> /tv/
    the home-screen app's name "TV test" / "TV (test)" -> "TV"
Its home-screen manifest and icons are its own (web-next/pwa, the tv. brand: tools/make_brand.py),
served under /tv/pwa/new/ - inside /tv/pwa/, which iOS fetches without credentials. The manifest
keeps id and scope /tv/, so the installed home-screen app stays one app whichever is chosen.
hls.js (/tv/static/vendor) is still the classic interface's copy (docs/INTERFACES.md).
Every __V__ becomes a hash of the source, so browsers and Cloudflare never mix two versions.

Refuses to finish (exit 1, OUT left absent) when anything is left unrewritten or unstamped, or when
the page or manifest points at a file the build doesn't contain. Prints the version on success.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".html", ".js", ".css", ".webmanifest"}
NAMES = [('"name": "TV (test)"', '"name": "TV"'), ('"short_name": "TV test"', '"short_name": "TV"'),
         (" - redesign preview", ""), ('name="apple-mobile-web-app-title" content="TV test"', 'name="apple-mobile-web-app-title" content="TV"')]
FAMILY_BASE = re.compile(r"^/[a-z0-9][a-z0-9-]{0,30}$")


def rewrites(base: str) -> list[tuple[str, str]]:
    if base in REWRITE:
        return REWRITE[base]
    if not FAMILY_BASE.match(base):
        raise ValueError(f"unknown base {base}")
    b = base                                                   # a family site: everything at its own address
    return [("NEXT = '/tv-test';", f"NEXT = '{b}/next';"), ("/tv-test/static", f"{b}/new/static"), ("/tv-test/pwa", f"{b}/pwa/new"),
            ("/tv-test/", f"{b}/"), ("'/tv/api'", f"'{b}/api'"), ("'/tv/static/vendor/", f"'{b}/static/vendor/"),
            ("export const FAMILY = false;", "export const FAMILY = true;"), *NAMES]


REWRITE = {
    "/tv-test": [],
    "/tv": [("NEXT = '/tv-test';", "NEXT = '/tv/next';"), ("/tv-test/static", "/tv/new/static"), ("/tv-test/pwa", "/tv/pwa/new"),
             ("/tv-test/", "/tv/"),
             # the home-screen app's name: the live one is "TV", as before
             ('"name": "TV (test)"', '"name": "TV"'), ('"short_name": "TV test"', '"short_name": "TV"'),
             (" - redesign preview", ""), ('name="apple-mobile-web-app-title" content="TV test"', 'name="apple-mobile-web-app-title" content="TV"')],
}
PREVIEW_WORDS = re.compile(r"TV test|TV \(test\)|redesign preview")


def version(src: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in src.rglob("*") if p.is_file() and "dev" not in p.relative_to(src).parts[:1]):
        h.update(f.read_bytes())
    return h.hexdigest()[:10]


def build(base: str, out: Path, src: Path = ROOT / "web-next", classic: Path = ROOT / "web") -> str:
    rules = rewrites(base)
    live = base != "/tv-test"                               # /tv or a family site: the classic files beside it
    v = version(src)
    stage = Path(tempfile.mkdtemp(prefix="ui-", dir=out.parent))
    try:
        shutil.copytree(src, stage, dirs_exist_ok=True, ignore=shutil.ignore_patterns("dev", ".DS_Store"))
        shutil.rmtree(stage / "dev", ignore_errors=True)
        problems = []
        for f in sorted(stage.rglob("*")):
            if not f.is_file() or f.suffix not in TEXT:
                continue
            text = f.read_text(encoding="utf-8")
            for a, b in rules:
                text = text.replace(a, b)
            text = text.replace("__V__", v)
            if live:                                        # the classic interface's files (hls.js): their own version
                for rel in set(re.findall(re.escape(base) + r"/static/([A-Za-z0-9._/-]+)\?v=" + v, text)):
                    f2 = classic / "static" / rel
                    if f2.is_file():
                        text = text.replace(f"{base}/static/{rel}?v={v}", f"{base}/static/{rel}?v={hashlib.sha256(f2.read_bytes()).hexdigest()[:10]}")
            f.write_text(text, encoding="utf-8")
            rel = f.relative_to(stage)
            if "__V__" in text:
                problems.append(f"{rel}: unstamped __V__")
            if live and PREVIEW_WORDS.search(text):
                problems.append(f"{rel}: preview wording left: {PREVIEW_WORDS.search(text).group()!r}")
            if live and "/tv-test" in text:
                problems.append(f"{rel}: /tv-test left: {text[text.index('/tv-test') - 30:text.index('/tv-test') + 30]!r}")
            if base not in REWRITE and ("'/tv/api'" in text or "'/tv/static/" in text):
                problems.append(f"{rel}: a /tv path left in a family site's build")
        problems += missing_assets(stage, base, classic)
        if problems:
            raise SystemExit("build_ui: refused\n  " + "\n  ".join(problems))
        for d in [stage, *(p for p in stage.rglob("*") if p.is_dir())]:
            d.chmod(0o755)
        for f in (p for p in stage.rglob("*") if p.is_file()):
            f.chmod(0o644)
        if out.exists():
            shutil.rmtree(out)
        stage.rename(out)
        return v
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def missing_assets(stage: Path, base: str, classic: Path) -> list[str]:
    """Files the page, the manifest and the scripts point at, where this build will find them: its own
    static/ and pwa/ (the preview), or for /tv its static/ under /tv/new and the classic interface's
    /tv/static and /tv/pwa."""
    where = ({f"{base}/new/static/": stage / "static", f"{base}/pwa/new/": stage / "pwa", f"{base}/static/": classic / "static"}
             if base != "/tv-test" else {f"{base}/static/": stage / "static", f"{base}/pwa/": stage / "pwa"})
    ref = re.compile("(" + "|".join(re.escape(k) for k in sorted(where, key=len, reverse=True)) + r")([A-Za-z0-9._/-]+)")
    out = []
    for f in [stage / "index.html", *(stage / "static" / "js").glob("*.js")]:
        if not f.exists():
            out.append(f"{f.relative_to(stage)} missing")
            continue
        for prefix, path in ref.findall(f.read_text(encoding="utf-8")):
            if f.suffix == ".js" and not path.endswith(".js"):
                continue                                    # paths built in code: checked where they're used
            if not (where[prefix] / path).is_file():
                out.append(f"{f.relative_to(stage)} -> {prefix}{path}: not found")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="/tv-test, /tv, or a family site's /<name>")
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    if a.base not in REWRITE and not FAMILY_BASE.match(a.base):
        ap.error(f"--base: /tv-test, /tv or /<name>, not {a.base}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    print(build(a.base, a.out.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
