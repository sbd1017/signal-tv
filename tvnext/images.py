"""Resized derivatives of catalogue artwork, generated once and kept on disk.

A request names an intent, not pixels: /tv-test/img/<variant>/<key>. The original comes from the
live app's own image proxy (/tv/api/img/<key>: catalogue URLs only, real images only, capped at
4 MB, cached by it). Each (variant, key) is resized at most once; afterwards it is a file read.

Guards: keys are the live app's 20-hex hashes; sources over 12 MB or 40 Mpx, or that are not
JPEG/PNG/WebP/GIF, are refused (the client falls back to the original); never upscaled; at most
RESIZE_WORKERS resizes at once and one per (variant, key) in flight; the cache is pruned
oldest-first above IMG_CACHE_MAX_MB.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from . import config

Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_SOURCE = 12 * 1024 * 1024
KEY = re.compile(r"^[0-9a-f]{16,40}$")
FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}

# name -> (max width, max height, WebP quality). Width-led for photos, square box for logos.
VARIANTS = {
    "hero": (1920, 1920, 78),          # desktop hero / details backdrop
    "hero-m": (1280, 1280, 78),        # laptop, tablet
    "hero-s": (828, 828, 76),          # phone, ambient light, placeholders
    "poster-s": (240, 360, 80),        # phone grid
    "poster": (400, 600, 80),          # desktop grid, shelves
    "poster-l": (600, 900, 82),        # details page poster
    "still": (480, 270, 80),           # episode stills
    "logo": (128, 128, 90),            # channel logos (keep alpha)
    "logo-l": (256, 256, 90),
}

_pool = ThreadPoolExecutor(max_workers=max(1, config.RESIZE_WORKERS), thread_name_prefix="resize")
_inflight: dict[tuple[str, str], asyncio.Future] = {}
stats = {"hits": 0, "made": 0, "refused": 0, "made_ms": 0.0, "bytes_in": 0, "bytes_out": 0}


def root() -> Path:
    return config.CACHE / "img"


def path_for(variant: str, key: str, ext: str) -> Path:
    return root() / variant / key[:2] / f"{key}.{ext}"


class Refused(Exception):
    """The source can't be turned into this derivative (bad key, not an image, too big...)."""


def render(data: bytes, variant: str, fmt: str = "webp") -> tuple[bytes, dict]:
    """Bytes of the derivative + facts about it. Runs in the worker pool."""
    w, h, q = VARIANTS[variant]
    if len(data) > MAX_SOURCE:
        raise Refused("source too large")
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in FORMATS:
            raise Refused(f"format {im.format}")
        src = im.size
        im.draft("RGB", (w * 2, h * 2))        # JPEG: decode at a reduced scale when that is enough
        im = ImageOps.exif_transpose(im)
        im.load()
    except Refused:
        raise
    except Exception as e:                     # decompression bomb, truncated file, not an image
        raise Refused(f"unreadable: {e.__class__.__name__}") from None
    alpha = im.mode in ("RGBA", "LA", "P") and ("transparency" in im.info or im.mode != "P")
    im = im.convert("RGBA" if alpha else "RGB")
    im.thumbnail((w, h), Image.LANCZOS)        # keeps aspect, never enlarges
    out = io.BytesIO()
    if fmt == "webp":
        im.save(out, "WEBP", quality=q, method=4)
    elif alpha:
        im.save(out, "PNG", optimize=True)
    else:
        im.save(out, "JPEG", quality=q + 4, optimize=True, progressive=True)
    return out.getvalue(), {"src": src, "size": im.size}


async def get(variant: str, key: str, webp: bool, client: httpx.AsyncClient) -> tuple[Path, str]:
    """Path of the derivative, making it first if needed. Raises Refused or httpx errors."""
    if variant not in VARIANTS or not KEY.match(key):
        raise Refused("unknown variant or key")
    fmt = "webp" if webp else "jpg"
    for ext in ((fmt,) if webp else ("jpg", "png")):
        p = path_for(variant, key, ext)
        if p.exists():
            stats["hits"] += 1
            _touch(p)
            return p, ext
    job = (variant, f"{key}.{fmt}")
    if job in _inflight:
        return await asyncio.shield(_inflight[job])
    fut = asyncio.get_running_loop().create_future()
    _inflight[job] = fut
    try:
        r = await client.get(f"{config.BACKEND}/tv/api/img/{key}", timeout=30)
        if r.status_code != 200:
            raise Refused(f"source HTTP {r.status_code}")
        t0 = time.perf_counter()
        data, facts = await asyncio.get_running_loop().run_in_executor(_pool, render, r.content, variant, fmt)
        ms = (time.perf_counter() - t0) * 1000
        ext = fmt if webp or data[:4] != b"\x89PNG" else "png"
        p = path_for(variant, key, ext)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        stats["made"] += 1
        stats["made_ms"] += ms
        stats["bytes_in"] += len(r.content)
        stats["bytes_out"] += len(data)
        fut.set_result((p, ext))
        return p, ext
    except Exception as e:
        if isinstance(e, Refused):
            stats["refused"] += 1
        fut.set_exception(e)
        fut.exception()                         # mark retrieved: waiters re-raise it
        raise
    finally:
        _inflight.pop(job, None)


def _touch(p: Path) -> None:
    """Mark as recently used (at most once a day per file) so pruning removes the oldest unused."""
    try:
        if time.time() - p.stat().st_mtime > 86400:
            os.utime(p)
    except OSError:
        pass


def usage() -> tuple[int, int]:
    files = size = 0
    for dirpath, _, names in os.walk(root()):
        for n in names:
            try:
                size += os.stat(os.path.join(dirpath, n)).st_size
                files += 1
            except OSError:
                pass
    return files, size


def prune(max_bytes: int | None = None) -> int:
    """Delete least recently used derivatives until the cache is under its cap. Returns bytes freed."""
    cap = (config.IMG_CACHE_MAX_MB if max_bytes is None else max_bytes / 1024 / 1024) * 1024 * 1024
    entries = []
    total = 0
    for dirpath, _, names in os.walk(root()):
        for n in names:
            fp = os.path.join(dirpath, n)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, fp))
            total += st.st_size
    freed = 0
    if total <= cap:
        return 0
    for _, size, fp in sorted(entries):
        if total - freed <= cap * 0.9:          # down to 90 %: no prune on every new file
            break
        try:
            os.remove(fp)
            freed += size
        except OSError:
            pass
    return freed
