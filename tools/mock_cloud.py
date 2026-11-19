#!/usr/bin/env python3
"""Loopback receiver with durable idempotency and a health endpoint."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--db", default="data/mock-cloud.sqlite3")
    args = parser.parse_args()
    from pathlib import Path
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as db:
        db.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

        class Handler(BaseHTTPRequestHandler):
            def respond(self, code, data):
                payload = json.dumps(data).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path != "/health":
                    self.respond(404, {})
                    return
                self.respond(200, {"stored": db.execute("SELECT count(*) FROM messages").fetchone()[0]})

            def do_POST(self):
                if self.path != "/events":
                    self.respond(404, {})
                    return
                try:
                    size = int(self.headers["Content-Length"])
                    if not 0 < size <= 65536:
                        raise ValueError("Invalid content length")
                    event = json.loads(self.rfile.read(size).decode("utf-8"))
                    event_id = self.headers["Idempotency-Key"]
                    if not isinstance(event_id, str) or event_id != event["id"]:
                        raise ValueError("Idempotency-Key must match event id")
                except (ValueError, TypeError, KeyError) as error:
                    self.respond(400, {"error": str(error)})
                    return
                with db:
                    db.execute("INSERT OR IGNORE INTO messages VALUES (?,?)", (event_id, json.dumps(event)))
                self.respond(200, {"id": event_id})

        with HTTPServer(("127.0.0.1", args.port), Handler) as server:
            print("Mock receiver ready on {}".format(server.server_port), flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
