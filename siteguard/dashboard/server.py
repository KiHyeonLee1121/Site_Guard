"""Low-bandwidth JPEG polling, read APIs and protected ROI editing."""

import base64
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
from socketserver import ThreadingMixIn
import sqlite3
from threading import BoundedSemaphore, Lock, Thread
from urllib.parse import urlsplit

STATIC = Path(__file__).resolve().parent / "static"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}
EVENT_ID = re.compile(r"/api/events/([0-9a-f-]{36})\Z")


def loopback(host):
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class DashboardState:
    def __init__(self, initial):
        self.data, self.jpeg = initial, None
        self.lock = Lock()

    def update(self, fields, jpeg=None, clear_image=False):
        with self.lock:
            self.data = dict(self.data, **fields)
            if jpeg is not None or clear_image:
                self.jpeg = jpeg

    def snapshot(self):
        with self.lock:
            return self.data, self.jpeg


class WebServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler):
        self.slots = BoundedSemaphore(16)
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        request.settimeout(3)
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Dashboard:
    def __init__(self, config, token, state, roi, database, policy):
        local = loopback(config["host"])
        if not local and len(token) < 24:
            raise ValueError("Set SITEGUARD_DASHBOARD_TOKEN (at least 24 characters) for a LAN bind.")
        auth = "Basic " + base64.b64encode(("siteguard:" + token).encode("utf-8")).decode("ascii")
        assets = {path: ((STATIC / filename).read_bytes(), content_type)
                  for path, (filename, content_type) in ASSETS.items()}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Polling would otherwise produce several messages a second.
                pass

            def respond(self, status, payload, content_type, forbidden=False):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                if forbidden:
                    self.send_header("WWW-Authenticate", 'Basic realm="SiteGuard", charset="UTF-8"')
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def json(self, status, payload, **kwargs):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.respond(status, encoded, "application/json; charset=utf-8", **kwargs)

            def authorized(self):
                host = self.headers.get("Host", "")
                try:
                    parsed = urlsplit("http://" + host)
                    valid_host = bool(parsed.hostname) and not (parsed.username or parsed.path or parsed.query or parsed.fragment)
                except ValueError:
                    valid_host = False
                if not valid_host or (local and not loopback(parsed.hostname)):
                    self.json(403, {"error": "Host is not allowed"})
                    return False
                credentials = self.headers.get("Authorization", "")
                if token and not hmac.compare_digest(credentials.encode("utf-8"), auth.encode("ascii")):
                    self.json(401, {"error": "Authentication required"}, forbidden=True)
                    return False
                return True

            def do_GET(self):
                if not self.authorized():
                    return
                path = urlsplit(self.path).path
                if path in assets:
                    data, content_type = assets[path]
                    self.respond(200, data, content_type + "; charset=utf-8")
                elif path == "/api/status":
                    self.json(200, state.snapshot()[0])
                elif path == "/api/frame.jpg":
                    jpeg = state.snapshot()[1]
                    if jpeg:
                        self.respond(200, jpeg, "image/jpeg")
                    else:
                        self.json(404, {"error": "No camera or video frame available"})
                elif path == "/api/roi":
                    revision, zones = roi.snapshot()
                    self.json(200, dict(zones, revision=revision))
                elif path == "/api/policy":
                    self.json(200, policy)
                elif path == "/api/events":
                    try:
                        self.json(200, {"events": database.recent()})
                    except sqlite3.Error:
                        self.json(503, {"error": "Event database unavailable"})
                else:
                    match = EVENT_ID.fullmatch(path)
                    if match:
                        try:
                            event = database.get(match.group(1))
                            if event:
                                self.json(200, event)
                                return
                        except sqlite3.Error:
                            self.json(503, {"error": "Event database unavailable"})
                            return
                    self.json(404, {"error": "Not found"})

            def do_PUT(self):
                if not self.authorized():
                    return
                if self.path != "/api/roi":
                    self.json(404, {"error": "Not found"})
                    return
                origin = self.headers.get("Origin")
                host = self.headers.get("Host")
                if (origin and origin not in ("http://" + host, "https://" + host)) or self.headers.get("X-SiteGuard-ROI") != "1":
                    self.json(403, {"error": "ROI updates require a same-origin editor request"})
                    return
                if self.headers.get_content_type() != "application/json":
                    self.json(415, {"error": "Expected JSON"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16384:
                        raise ValueError("Unexpected request length")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
                        raise ValueError("Current ROI revision is required")
                    revision = roi.save(payload, payload["revision"])
                    self.json(200, {"saved": True, "revision": revision})
                except (ValueError, UnicodeError) as error:
                    self.json(400, {"error": str(error)})
                except OSError:
                    self.json(503, {"error": "Could not persist ROI settings"})

        self.http = WebServer((config["host"], config["port"]), Handler)
        self.thread = Thread(target=self.http.serve_forever, daemon=True, name="dashboard")
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(1)
