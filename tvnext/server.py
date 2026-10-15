"""HTTP for the sidecar. nginx sends /tv-test/img/, /tv-test/art/ and /tv-test/api/ here (the preview,
behind the site's login) and, once the new interface serves /tv, the same under /tv/next/ (behind
/tv's own login: the site password or a remembered device). /internal/* is only answered on loopback
without a proxy (maintenance from the Pi)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from tvapp import sports

from . import config, fixtures, images, sportsart

log = logging.getLogger("tvnext")
IMMUTABLE = "private, max-age=31536000, immutable"
ID = re.compile(r"^(team|comp):[a-z0-9-]{1,60}$")
PREFIXES = ("/tv-test", "/tv/next", *config.SITES)   # the preview, the live interface, the family sites (deploy/build_ui.py)
GAP_ID = re.compile(r"^(team|comp|name):[\w -]{1,60}$")


class S:
    client: httpx.AsyncClient
    lib: sportsart.Library
    acq: sportsart.Acquirer
    fix: fixtures.Fixtures
    flushed = 0.0


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    S.client = httpx.AsyncClient(follow_redirects=False, limits=httpx.Limits(max_connections=8))
    S.lib = sportsart.Library()
    S.acq = sportsart.Acquirer(S.lib, S.client)
    S.fix = fixtures.Fixtures(S.lib, S.acq.src, config.STATE / "fixtures.json")
    tasks = [asyncio.create_task(S.acq.run()), asyncio.create_task(S.fix.run()), asyncio.create_task(_housekeeping())]
    yield
    S.lib.gaps.flush()
    S.fix.flush()
    for t in tasks:
        t.cancel()
    await S.client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def route(method: str, path: str):
    """The same handler under every prefix the interface can be served from."""
    def add(fn):
        for prefix in PREFIXES:
            app.add_api_route(prefix + path, fn, methods=[method])
        return fn
    return add


async def _housekeeping():
    while True:
        await asyncio.sleep(600)
        try:
            freed = await asyncio.to_thread(images.prune)
            if freed:
                log.info("image cache pruned: %d MB freed", freed // 1048576)
            if config.ART_MODE == "refresh":
                await S.acq.refresh_old()
            S.lib.gaps.reconcile(S.lib.index())
            S.lib.gaps.flush()
        except Exception as e:                     # housekeeping must never stop the service
            log.warning("housekeeping: %s", e)


# ------------------------------------------------------------------ images
@route("GET", "/img/{variant}/{key}")
async def image(variant: str, key: str, request: Request):
    webp = "image/webp" in request.headers.get("accept", "") or "image/*" in request.headers.get("accept", "")
    try:
        site = next((p for p in config.SITES if request.url.path.startswith(p + "/")), None)     # a family site's own logos
        path, ext = await images.get(variant, key, webp, S.client, config.SITES[site] if site else None)
    except images.Refused as e:
        return Response(f"refused: {e}", status_code=422, media_type="text/plain", headers={"Cache-Control": "no-store"})
    except httpx.HTTPError:
        return Response("source unavailable", status_code=502, media_type="text/plain", headers={"Cache-Control": "no-store"})
    media = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}[ext]
    return FileResponse(path, media_type=media, headers={"Cache-Control": IMMUTABLE, "Vary": "Accept"})


# ------------------------------------------------------------------ sports artwork
@route("GET", "/api/art")
async def art_index(ids: str = "", names: str = ""):
    """Which of these entities have artwork (served from the Pi); the rest are queued for lookup.
    names: team names as the guide shows them (newline-separated) for matches the live app sent
    without ids - resolved with this build's own dataset, so teams added here get their crest before
    the live app knows them."""
    resolved = {}
    for label in [n.strip() for n in names.split("\n") if n.strip()][:100]:
        i, _, _ = sports.resolve_side(label[:80])
        if i >= 0 and sports.ENTITIES[i].kind in ("club", "national"):
            resolved[label] = sports.ENTITIES[i].key
    want = [i for i in dict.fromkeys([*ids.split(","), *resolved.values()]) if ID.match(i)][:300]
    idx = S.lib.index()
    queued = S.acq.enqueue([i for i in want if i not in idx]) if config.ART_MODE != "remote" else 0
    return JSONResponse({"items": {i: idx[i] for i in want if i in idx}, "names": resolved, "queued": queued, "pending": S.acq.q.qsize()},
                        headers={"Cache-Control": "no-store"})


@route("GET", "/api/fixtures")
async def fixtures_index(q: str = ""):
    """Live or replay, from the real fixture dates (tvnext/fixtures.py). q: "home|away|start" items,
    comma-separated, team ids as the Sports API gives them; at most 80. Answers what is known now
    and queues the rest; "pending" says how many lookups are still waiting."""
    items = []
    for part in q.split(",")[:80]:
        bits = part.split("|")
        if len(bits) == 3 and ID.match(bits[0]) and ID.match(bits[1]) and bits[2].isdigit() and bits[0].startswith("team:"):
            items.append((bits[0], bits[1], int(bits[2])))
    if config.ART_MODE == "remote":
        return JSONResponse({"items": {}, "pending": 0}, headers={"Cache-Control": "no-store"})
    found, pending = S.fix.ask(items)
    return JSONResponse({"items": found, "pending": pending}, headers={"Cache-Control": "no-store"})


@route("POST", "/api/art/gaps")
async def art_gaps(request: Request):
    """The page drew these with a generated crest / mark: {items: [{id, name, context, competition, reason}]}.
    The page sends each entity + context once per load; the registry keeps one record per entity."""
    if "application/json" not in request.headers.get("content-type", ""):
        return Response(status_code=415)
    try:
        items = (await request.json()).get("items") or []
    except ValueError:
        return Response(status_code=400)
    n = 0
    for it in items[:200] if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        eid, name = str(it.get("id") or ""), str(it.get("name") or "")[:80].strip()
        if eid == "name:" and name:                      # an unlisted team: keyed by its normalised words
            i, key, _ = sports.resolve_side(name)
            if i >= 0 or not key or key.isdigit():
                continue
            eid = f"name:{key[:60]}"
        if not GAP_ID.match(eid) or (eid.startswith(("team:", "comp:")) and eid not in sportsart.entities()):
            continue
        reason = sportsart.gap_reason(S.lib, eid, str(it.get("reason") or ""), S.acq.queued)
        if reason is None:
            continue
        ents = sportsart.entities()
        shown = ents[eid]["names"][0] if eid in ents else name
        S.lib.gaps.record(eid, shown, str(it.get("context") or "")[:30], str(it.get("competition") or "")[:60], reason)
        n += 1
    if n and time.monotonic() - S.flushed > 60:        # at most a write a minute (and on housekeeping / shutdown)
        S.lib.gaps.flush()
        S.flushed = time.monotonic()
    return JSONResponse({"recorded": n}, headers={"Cache-Control": "no-store"})


@route("GET", "/api/art/gaps")
async def art_gaps_list(kind: str = "", state: str = "open", sort: str = "seen"):
    """The registry for the Settings > Artwork list (same login as the page)."""
    kind = kind if kind in ("team", "comp") else ""
    state = state if state in ("open", "resolved", "all") else "open"
    S.lib.gaps.reconcile(S.lib.index())
    r = sportsart.missing(S.lib, None, kind, state, "recent" if sort == "recent" else "seen")
    return JSONResponse({k: r[k] for k in ("at", "coverage", "gaps", "gaps_open", "gaps_resolved")}, headers={"Cache-Control": "no-store"})


@route("GET", "/art/{kind}/{name}/{size}.webp")
async def art_file(kind: str, name: str, size: int):
    if kind not in ("teams", "competitions") or not re.match(r"^[a-z0-9-]{1,60}$", name):
        return Response(status_code=404)
    eid = f"{'comp' if kind == 'competitions' else 'team'}:{name}"
    if config.ART_MODE == "remote":                 # development: fetch, don't keep
        got = await sportsart.acquire(eid, S.lib, S.acq.src, persist=False)
        if not got:
            return Response(status_code=404)
        return Response(got["data"], media_type="image/png", headers={"Cache-Control": "no-store"})
    p = await asyncio.to_thread(S.lib.derivative, eid, size)
    if not p:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": IMMUTABLE})


# ------------------------------------------------------------------ maintenance (loopback only)
def _local(request: Request) -> bool:
    return request.client and request.client.host in ("127.0.0.1", "::1") and "x-forwarded-for" not in request.headers


@app.get("/internal/{action}")
async def internal(action: str, request: Request, id: str = "", limit: int = 0):
    if not _local(request):
        return Response(status_code=404)
    if action == "status":
        files, size = await asyncio.to_thread(images.usage)
        ents = sportsart.entities()
        idx = S.lib.index()
        return {"mode": config.ART_MODE, "art": {"cached": len(idx), "teams": sum(i.startswith("team:") for i in idx),
                "competitions": sum(i.startswith("comp:") for i in idx), "misses": len(S.lib.misses()),
                "canonical_teams": sum(e["kind"] == "team" for e in ents.values()), "canonical_competitions": sum(e["kind"] == "comp" for e in ents.values()),
                "queue": S.acq.q.qsize(), "done": S.acq.done, "api_calls": S.acq.calls, "disk": S.lib.usage(),
                "gaps": {"open": sum(g["status"] == "open" for g in S.lib.gaps.data.values()), "recorded": len(S.lib.gaps.data)}},
                "images": {**images.stats, "files": files, "bytes": size}}
    if action == "prewarm":
        order = sportsart.prewarm_order()
        return {"queued": S.acq.enqueue(order[:limit] if limit else order)}
    if action == "refresh" and ID.match(id):          # look one entity up again now
        S.lib.clear(id)
        return {"queued": S.acq.enqueue([id])}
    if action == "clear" and ID.match(id):            # forget a broken mapping (and its miss record)
        S.lib.clear(id)
        return {"cleared": id}
    if action == "clear-derivatives":
        return {"cleared": await asyncio.to_thread(S.lib.clear_derivatives)}
    if action == "refresh-old":
        return {"checked": await S.acq.refresh_old()}
    if action == "prune-images":
        return {"freed": await asyncio.to_thread(images.prune)}
    if action == "misses":
        return S.lib.misses()
    if action == "retry-misses":                      # look every miss (or one) up again now, e.g. after adding a source
        gone = S.lib.forget_misses([id] if ID.match(id) else None)
        return {"forgotten": len(gone), "queued": S.acq.enqueue(gone)}
    if action == "missing":                           # iptv artwork missing
        q = request.query_params
        events = await _guide()
        r = sportsart.missing(S.lib, events, q.get("kind", "") if q.get("kind") in ("team", "comp") else "",
                              q.get("state") if q.get("state") in ("open", "resolved", "all") else "open",
                              "recent" if q.get("sort") == "recent" else "seen")
        if q.get("format") == "json":
            return r
        return PlainTextResponse(sportsart.format_missing(r, limit or 40))
    return Response(status_code=404)


async def _guide() -> list[dict] | None:
    """Today's and tomorrow's Sports events from the live app (read only), for the gaps report."""
    out = []
    try:
        for day in ("today", "tomorrow"):
            r = await S.client.get(f"{config.BACKEND}/tv/api/sports", params={"day": day}, timeout=30)
            r.raise_for_status()
            out += r.json().get("events") or []
    except (httpx.HTTPError, ValueError):
        return None
    return out
