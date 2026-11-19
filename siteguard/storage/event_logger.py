"""Persist state transitions immediately and attach asynchronous hardware results."""

from datetime import datetime, timezone
import logging
import sqlite3
import time
from uuid import uuid4

LOG = logging.getLogger("siteguard.events")


class EventLogger:
    def __init__(self, database, source, cloud):
        self.database, self.source, self.cloud = database, source, cloud
        self.errors = 0

    def write(self, kind, timestamp, track=None, output=None, command=None, clip=False, detail=None):
        now = time.time()
        item = {"id": str(uuid4()), "utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "kind": kind, "source": self.source, "source_time_s": timestamp,
                "track": track._asdict() if track else None,
                "output": output._asdict() if output else None, "detail": detail}
        try:
            self.database.add(item, self.cloud, command, clip, now)
        except sqlite3.Error:
            self.errors += 1
            if self.errors == 1 or self.errors % 100 == 0:
                LOG.exception("Event storage failed (%s total). Local alarm remains active.", self.errors)
            return None
        LOG.info("%s track=%s command=%s", kind, track.track_id if track else "-", command or "-")
        return item["id"]

    def update(self, method, *args):
        try:
            getattr(self.database, method)(*args)
        except sqlite3.Error:
            self.errors += 1
            LOG.exception("SQLite update failed: %s", method)
