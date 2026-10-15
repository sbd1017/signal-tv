"""Local preview of web-next (the /tv-test interface) against a running backend.

    ssh -f -N -L 8790:127.0.0.1:8790 -L 8792:127.0.0.1:8792 pi   # the real app + the tvnext sidecar
    python3 tools/devproxy.py [port] [--read-only]                  # then open http://localhost:8797/tv-test/

--read-only refuses every write to the synced state (POST /tv/api/state) and to the Pi's artwork-gap
registry (POST /tv-test/api/art/gaps): use it for testing and screenshots, so nothing done here
changes the viewer's favourites, preferences or history, or counts as real use.
--sidecar-writes lets writes through to the sidecar while /tv/ stays read-only: only for testing the
gap registry against an isolated sidecar (TV_SIDECAR pointing at a temporary-state instance).

/tv-test/... is served from web-next/ (no caching, same CSP as the live site); everything
under /tv/ (API, artwork, media) is streamed through to TV_BACKEND (default 127.0.0.1:8790).
The Host header is passed on unchanged, so the backend's same-site Origin check for state
writes accepts this page exactly as it accepts example.com.
"""
import http.client
import http.server
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web-next")
BACKEND = os.environ.get("TV_BACKEND", "127.0.0.1:8790")
SIDECAR = os.environ.get("TV_SIDECAR", "127.0.0.1:8792")              # tvnext: /tv-test/img|art|api
READ_ONLY = "--read-only" in sys.argv
SIDECAR_WRITES = "--sidecar-writes" in sys.argv
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; manifest-src 'self'; font-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".png": "image/png", ".webmanifest": "application/manifest+json", ".json": "application/json",
         ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization", "proxy-authenticate"}


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if not self.path.startswith("/tv/m/"):
            sys.stderr.write("%s\n" % (fmt % args))

    def do_GET(self):
        self.route()

    def do_HEAD(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/tv-test"):
            self.send_response(308)
            self.send_header("Location", "/tv-test/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path.startswith(("/tv-test/img/", "/tv-test/art/", "/tv-test/api/", "/tv/next/")):
            if READ_ONLY and not SIDECAR_WRITES and self.command not in ("GET", "HEAD"):
                self.send_error(403, "read-only preview: the artwork-gap registry is not changed")
                return
            self.proxy(SIDECAR)
        elif path.startswith("/tv-test/"):
            self.static(path[len("/tv-test/"):] or "index.html")
        elif path.startswith("/tv/"):
            if READ_ONLY and self.command not in ("GET", "HEAD"):
                self.send_error(403, "read-only preview: synced state is not changed")
                return
            self.proxy(BACKEND)
        else:
            self.send_error(404)

    def static(self, rel):
        full = os.path.realpath(os.path.join(ROOT, rel))
        if not full.startswith(os.path.realpath(ROOT) + os.sep) or not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def proxy(self, upstream):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        conn = http.client.HTTPConnection(upstream, timeout=120)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            r = conn.getresponse()
        except OSError as e:
            self.send_error(502, f"backend unreachable ({e}) - is the SSH tunnel up?")
            return
        self.send_response(r.status, r.reason)
        chunked = r.getheader("Content-Length") is None and self.command != "HEAD" and r.status not in (204, 304)
        for k, v in r.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                buf = r.read1(65536) if hasattr(r, "read1") else r.read(65536)
                if not buf:
                    break
                if chunked:
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(buf), buf))
                else:
                    self.wfile.write(buf)
            if chunked:
                self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()


if __name__ == "__main__":
    port = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8797)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
