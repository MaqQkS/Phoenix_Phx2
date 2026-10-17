"""PHX2 dashboard server — READ-ONLY, localhost-only.

Serves the static Phoenix dashboard plus a single JSON endpoint
(``/api/xdata``) built by :mod:`PHX2.dashboard.adapter` from the real
producer / paper artifact directories.

Safety properties:
  * GET / HEAD only — every other HTTP method gets ``405 read-only``.
  * Binds 127.0.0.1 by default; never exposes anything beyond localhost.
  * Static file serving is jailed to the ``static/`` directory (no traversal).
  * The API reads only allowlisted artifact files (see adapter) — it cannot
    dispatch, write, sign, trade, or touch any ledger.

Run:
    python -m PHX2.dashboard.server
    python -m PHX2.dashboard.server --port 8642 --producer-dir <dir> --paper-dir <dir>
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):  # ``python server.py`` fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from PHX2.dashboard import adapter  # type: ignore
else:
    from . import adapter

STATIC_ROOT = Path(__file__).resolve().parent / "static"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8642,
    "producer_dir": r"C:\Users\BalaC\phx2_live_free_tier\out\live_private_01",
    "paper_dir": r"C:\Users\BalaC\phx2_paper_trading\live_free_tier_private_01",
    "ledger_path": r"C:\Users\BalaC\phx2_live_free_tier\ping_dedupe.jsonl",
    # OPTIONAL operator-entered Helius credits (manual; never auto-read, never a secret/API key).
    # Shape in config.json: {"before": <int>, "after": <int>, "window_seconds": <int>,
    #                        "as_of_utc": "<iso>"}. Absent => the credit panel shows "not provided".
    "helius_credits": None,
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".jsx": "text/babel; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def is_loopback_host(host):
    """True only for localhost or a numeric loopback address."""
    if str(host).strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host).strip()).is_loopback
    except ValueError:
        return False


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.is_file():
        try:
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key in cfg:
                if key in file_cfg and file_cfg[key] is not None:
                    cfg[key] = file_cfg[key]
        except (OSError, ValueError) as exc:
            print(f"[dashboard] WARNING: bad config.json ignored ({exc})", file=sys.stderr)
    return cfg


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "PHX2Dashboard/1.0"
    config: dict = {}

    # ── read-only enforcement ────────────────────────────────────────────
    def _reject_write(self):
        body = b'{"error": "read-only dashboard: only GET is allowed"}'
        self.send_response(405, "Method Not Allowed")
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = _reject_write
    do_PUT = _reject_write
    do_DELETE = _reject_write
    do_PATCH = _reject_write
    do_OPTIONS = _reject_write

    # ── GET routing ──────────────────────────────────────────────────────
    def do_GET(self):
        self._serve(head_only=False)

    def do_HEAD(self):
        self._serve(head_only=True)

    def _serve(self, head_only):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        try:
            if path == "/api/xdata":
                self._serve_xdata(head_only)
            elif path == "/api/health":
                self._serve_health(head_only)
            else:
                self._serve_static(path, head_only)
        except BrokenPipeError:
            pass
        except ConnectionAbortedError:
            pass
        except Exception as exc:  # never crash the server on one request
            try:
                self._send_json(500, {"error": f"internal: {exc.__class__.__name__}"},
                                head_only)
            except OSError:
                pass

    def _send_json(self, status, obj, head_only):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve_xdata(self, head_only):
        cfg = self.config
        bundle = adapter.build_bundle(
            cfg["producer_dir"], cfg["paper_dir"], ledger_path=cfg.get("ledger_path"),
            helius_credits=cfg.get("helius_credits"))
        self._send_json(200, bundle, head_only)

    def _serve_health(self, head_only):
        self._send_json(200, {
            "ok": True,
            "read_only": True,
            "producer_dir": self.config["producer_dir"],
            "paper_dir": self.config["paper_dir"],
        }, head_only)

    def _serve_static(self, path, head_only):
        rel = path.lstrip("/") or "index.html"
        target = (STATIC_ROOT / rel).resolve()
        # jail to static root — no traversal, no symlink escape
        if not str(target).startswith(str(STATIC_ROOT.resolve())):
            self._send_json(403, {"error": "forbidden"}, head_only)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send_json(404, {"error": "not found"}, head_only)
            return
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        # keep API polling quiet; log everything else
        if "/api/xdata" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main(argv=None):
    cfg = load_config()
    parser = argparse.ArgumentParser(description="PHX2 read-only dashboard server")
    parser.add_argument("--host", default=cfg["host"])
    parser.add_argument("--port", type=int, default=cfg["port"])
    parser.add_argument("--producer-dir", default=cfg["producer_dir"])
    parser.add_argument("--paper-dir", default=cfg["paper_dir"])
    parser.add_argument("--ledger-path", default=cfg.get("ledger_path"))
    parser.add_argument("--stop-file", type=Path,
                        help="cooperative supervisor stop seam")
    args = parser.parse_args(argv)
    if not is_loopback_host(args.host):
        parser.error("--host must be loopback-only (127.0.0.1, ::1, or localhost)")

    DashboardHandler.config = {
        "producer_dir": args.producer_dir,
        "paper_dir": args.paper_dir,
        "ledger_path": args.ledger_path,
        # manual, operator-entered credit values from config.json (no CLI flag; never a secret)
        "helius_credits": cfg.get("helius_credits"),
    }
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"[dashboard] READ-ONLY server on http://{args.host}:{args.port}")
    print(f"[dashboard] producer_dir = {args.producer_dir}")
    print(f"[dashboard] paper_dir    = {args.paper_dir}")
    print(f"[dashboard] ledger_path  = {args.ledger_path} (line-count only)")
    print("[dashboard] GET/HEAD only · no dispatch · no wallet · no writes")
    watcher_stop = threading.Event()
    watcher = None
    if args.stop_file is not None:
        def _watch_stop_file():
            while not watcher_stop.wait(0.5):
                try:
                    if args.stop_file.exists():
                        server.shutdown()
                        return
                except OSError:
                    continue

        watcher = threading.Thread(
            target=_watch_stop_file,
            name="phx2-dashboard-stop-watcher",
            daemon=True,
        )
        watcher.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopped")
    finally:
        watcher_stop.set()
        server.server_close()
        if watcher is not None:
            watcher.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
