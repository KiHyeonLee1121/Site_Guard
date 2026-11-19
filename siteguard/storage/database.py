"""SQLite event ledger and durable cloud outbox in the same transaction."""

import json
from pathlib import Path
import sqlite3
from threading import RLock
import time


class Database:
    def __init__(self, path):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=1.0, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.lock, self.connection as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    created REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    command_id TEXT,
                    response TEXT,
                    clip TEXT,
                    clip_pending INTEGER NOT NULL DEFAULT 0,
                    cloud_status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS event_time ON events(created DESC);
                CREATE INDEX IF NOT EXISTS cloud_due ON events(cloud_status, next_attempt, created);
                CREATE INDEX IF NOT EXISTS commands ON events(command_id);
            """)
            conn.execute("UPDATE events SET response=? WHERE command_id IS NOT NULL AND response IS NULL",
                         (json.dumps({"ok": False, "error": "process_restarted"}),))
            conn.execute("UPDATE events SET clip_pending=0 WHERE clip_pending=1")

    def add(self, payload, cloud=False, command_id=None, clip_pending=False, now=None):
        created = time.time() if now is None else now
        with self.lock, self.connection as conn:
            conn.execute("""
                INSERT INTO events(id,created,kind,payload,command_id,clip_pending,cloud_status)
                VALUES (?,?,?,?,?,?,?)
            """, (payload["id"], created, payload["kind"], json.dumps(payload, ensure_ascii=False),
                  command_id, int(clip_pending), "pending" if cloud else "disabled"))

    @staticmethod
    def unpack(row):
        payload = json.loads(row["payload"])
        payload.update(local_status="stored", command_id=row["command_id"],
                       arduino_response=json.loads(row["response"]) if row["response"] else None,
                       clip=row["clip"], clip_pending=bool(row["clip_pending"]),
                       cloud_status=row["cloud_status"], attempts=row["attempts"], last_error=row["last_error"])
        return payload

    def recent(self, limit=50):
        with self.lock:
            rows = self.connection.execute("SELECT * FROM events ORDER BY created DESC, rowid DESC LIMIT ?",
                                           (limit,)).fetchall()
        return [self.unpack(row) for row in rows]

    def get(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT * FROM events WHERE id=?", (identifier,)).fetchone()
        return self.unpack(row) if row else None

    def save_response(self, value):
        with self.lock, self.connection as conn:
            conn.execute("UPDATE events SET response=? WHERE command_id=?", (json.dumps(value), value["id"]))

    def save_clip(self, identifiers, filename):
        with self.lock, self.connection as conn:
            conn.executemany("UPDATE events SET clip=?, clip_pending=0 WHERE id=?",
                             [(filename, identifier) for identifier in identifiers])

    def forget_clips(self, filenames):
        with self.lock, self.connection as conn:
            conn.executemany("UPDATE events SET clip=NULL WHERE clip=?", [(name,) for name in filenames])

    def due(self, now, limit=12):
        with self.lock:
            rows = self.connection.execute("""
                SELECT * FROM events WHERE cloud_status='pending' AND next_attempt<=?
                AND (command_id IS NULL OR response IS NOT NULL OR created<?)
                ORDER BY next_attempt,created LIMIT ?
            """, (now, now - 15, limit)).fetchall()
        return [self.unpack(row) for row in rows]

    def mark_sent(self, identifier):
        with self.lock, self.connection as conn:
            conn.execute("UPDATE events SET cloud_status='sent',last_error=NULL WHERE id=?", (identifier,))

    def mark_retry(self, identifier, when, error):
        with self.lock, self.connection as conn:
            conn.execute("UPDATE events SET attempts=attempts+1,next_attempt=?,last_error=? WHERE id=?",
                         (when, error[:240], identifier))

    def prune(self, before, max_events):
        with self.lock, self.connection as conn:
            conn.execute("DELETE FROM events WHERE created<?", (before,))
            conn.execute("""
                DELETE FROM events WHERE id IN (
                    SELECT id FROM events ORDER BY created DESC, rowid DESC LIMIT -1 OFFSET ?
                )
            """, (max_events,))

    def queue_state(self):
        with self.lock:
            return self.connection.execute("SELECT count(*) FROM events WHERE cloud_status='pending'").fetchone()[0]

    def close(self):
        with self.lock:
            self.connection.close()
