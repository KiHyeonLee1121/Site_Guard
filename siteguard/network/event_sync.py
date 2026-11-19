"""Retry saved events on a worker. Event ID is the receiver idempotency key."""

import logging
import sqlite3
from threading import Event, Thread
import time

LOG = logging.getLogger("siteguard.sync")


class EventSync:
    def __init__(self, database, client, config):
        self.database, self.client, self.config = database, client, config
        self.stop = Event()
        self.status = "queued" if client else "waiting_for_gateway"
        self.thread = None

    def once(self, now=None):
        now = time.time() if now is None else now
        if self.client is None:
            return 0
        sent = 0
        for event in self.database.due(now):
            if self.stop.is_set():
                break
            try:
                self.client.send(event)
            except (OSError, ValueError) as error:
                delay = min(self.config["retry_max_sec"],
                            self.config["retry_base_sec"] * 2 ** min(event["attempts"], 20))
                self.database.mark_retry(event["id"], now + delay, str(error).split("?")[0])
                if self.status != "offline":
                    LOG.warning("Cloud unavailable; queued events will be retried: %s", type(error).__name__)
                self.status = "offline"
                # One failed request per pass bounds network work while disconnected.
                break
            self.database.mark_sent(event["id"])
            self.status = "online"
            sent += 1
        return sent

    def _run(self):
        while not self.stop.is_set():
            try:
                self.once()
            except sqlite3.Error:
                LOG.exception("Cloud queue storage issue")
            self.stop.wait(0.5)

    def start(self):
        if self.client is not None:
            self.thread = Thread(target=self._run, name="event-sync", daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(self.config["timeout"] + 0.5)
