"""Settings from the environment (the systemd unit sets them; defaults suit local tests)."""
import os
from pathlib import Path

STATE = Path(os.environ.get("TVN_STATE", "/var/lib/signal-tv-next"))       # durable: sports artwork library
CACHE = Path(os.environ.get("TVN_CACHE", "/var/cache/signal-tv-next"))     # regenerable: image derivatives
BACKEND = os.environ.get("TVN_BACKEND", "http://127.0.0.1:8790")            # the live app (read only)
IMG_CACHE_MAX_MB = int(os.environ.get("TVN_IMG_CACHE_MAX_MB", "1500"))      # derivatives, pruned oldest-first
RESIZE_WORKERS = int(os.environ.get("TVN_RESIZE_WORKERS", "2"))             # concurrent resizes (Pi: 4 cores)
# cached: use the library, acquire missing artwork in the background (default)
# refresh: as cached, and also re-check artwork older than ART_REFRESH_DAYS
# remote: development only - every artwork request asks the source again; nothing is kept
ART_MODE = os.environ.get("TVN_ART_MODE", "cached")
ART_REFRESH_DAYS = int(os.environ.get("TVN_ART_REFRESH_DAYS", "120"))
ART_MISS_RETRY_DAYS = int(os.environ.get("TVN_ART_MISS_RETRY_DAYS", "14"))
TSDB_BASE = os.environ.get("TVN_TSDB_BASE", "https://www.thesportsdb.com/api/v1/json")
TSDB_KEY = os.environ.get("TVN_TSDB_KEY", "123")                              # TheSportsDB's free key
TSDB_INTERVAL = float(os.environ.get("TVN_TSDB_INTERVAL", "2.2"))            # seconds between API calls (free: 30/min)
# artwork sources, asked in this order (sportsart.py); drop one to stop using it
ART_SOURCES = [s.strip() for s in os.environ.get("TVN_ART_SOURCES", "thesportsdb,espn,wikidata").split(",") if s.strip()]
ESPN_INTERVAL = float(os.environ.get("TVN_ESPN_INTERVAL", "1.5"))            # seconds between ESPN API calls
WIKI_INTERVAL = float(os.environ.get("TVN_WIKI_INTERVAL", "1.0"))            # Wikidata / Commons API
# who to contact about the artwork lookups: Wikimedia asks every client to name one (a site or an email)
ART_CONTACT = os.environ.get("TVN_ART_CONTACT", "https://example.com")
