"""Local web server for the map. Stdlib only, bound to 127.0.0.1.

GET  /               the page (static/index.html)
GET  /api/topology   the last build, plus sprint lanes
POST /api/rebuild    rebuild in-process, then return the new topology

Run: python -m planmap.server --root <project> --port <n>
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import build as B, config as C, sprint as S

STATIC = Path(__file__).resolve().parent / "static"


def payload(root):
    topo = json.loads((C.out_dir(root) / "topology.json").read_text(encoding="utf-8"))
    topo["sprint"] = S.lanes(topo)
    return topo


def make_handler(root):
    class Handler(BaseHTTPRequestHandler):
        server_version = "planmap"

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

        def _host_ok(self):
            return (self.headers.get("Host") or "").split(":")[0] in ("localhost", "127.0.0.1")

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body)
            if isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "host"})
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/api/topology":
                    return self._send(200, payload(root))
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": type(e).__name__})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "host"})
            if self.path.split("?")[0] != "/api/rebuild":
                return self._send(404, {"error": "not found"})
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "json only"})
            try:
                B.write(root, C.load(root))
                return self._send(200, payload(root))
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def serve(root, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Path(root)))
    print(f"planmap on http://localhost:{port}", flush=True)
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, default=C.DEFAULTS["port"])
    a = ap.parse_args()
    serve(a.root, a.port)


if __name__ == "__main__":
    main()
