"""Bounded event video buffer and asynchronous AVI writing."""

from collections import deque
import logging
import os
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import time

from siteguard.vision.sources import open_cv

LOG = logging.getLogger("siteguard.recording")


class VideoRecorder:
    def __init__(self, config):
        self.config = config
        self.cv = open_cv()
        self.root = Path(config["directory"])
        self.root.mkdir(parents=True, exist_ok=True)
        self.ring, self.pending = deque(), None
        self.ring_bytes = 0
        self.last_sample = None
        self.jobs, self.results = Queue(3), Queue(12)
        self.stop = Event()
        self.thread = Thread(target=self._run, name="event-recorder", daemon=True)
        self.thread.start()

    def observe(self, frame):
        now = frame.timestamp
        if self.pending and now > self.pending["until"]:
            self._dispatch()
        if frame.image is None or (self.last_sample is not None and now - self.last_sample + 1e-9 < 1 / self.config["fps"]):
            return
        self.last_sample = now
        width = min(frame.width, self.config["width"])
        height = max(2, round(frame.height * width / frame.width))
        image = self.cv.resize(frame.image, (width, height)) if (width, height) != (frame.width, frame.height) else frame.image
        ok, jpg = self.cv.imencode(".jpg", image, [self.cv.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return
        content = jpg.tobytes()
        limit = self.config["buffer_bytes"]
        if len(content) > limit:
            return
        self.ring.append((now, content))
        self.ring_bytes += len(content)
        while self.ring and (self.ring_bytes > limit or now - self.ring[0][0] > self.config["pre_sec"]):
            self.ring_bytes -= len(self.ring.popleft()[1])
        if self.pending:
            if self.pending["size"] + len(content) <= limit:
                self.pending["frames"].append(content)
                self.pending["size"] += len(content)
            else:
                self._dispatch()

    def mark(self, identifiers, timestamp):
        if not identifiers:
            return
        if self.pending is not None:
            if len(self.pending["ids"]) + len(identifiers) <= 128:
                self.pending["ids"].extend(identifiers)
                return
            self._dispatch()
        self.pending = {"ids": list(identifiers), "until": timestamp + self.config["post_sec"],
                        "frames": [data for _, data in self.ring], "size": self.ring_bytes}

    def _dispatch(self):
        job, self.pending = self.pending, None
        try:
            self.jobs.put_nowait(job)
        except Full:
            LOG.warning("Clip writer queue full; keeping event metadata for %s", job["ids"][0])
            self._result(job["ids"], None, [])

    def _result(self, identifiers, path, removed):
        try:
            self.results.put_nowait((identifiers, path, removed))
        except Full:
            LOG.error("Clip result queue full for %s", identifiers)

    def _write(self, job):
        import numpy as np
        filename = job["ids"][0] + ".avi"
        final = self.root / filename
        temporary = self.root / (job["ids"][0] + ".part.avi")
        writer, size = None, None
        try:
            for content in job["frames"]:
                image = self.cv.imdecode(np.frombuffer(content, np.uint8), self.cv.IMREAD_COLOR)
                if image is None:
                    continue
                if writer is None:
                    height, width = image.shape[:2]
                    size = (max(2, width - width % 2), max(2, height - height % 2))
                    writer = self.cv.VideoWriter(str(temporary), self.cv.VideoWriter_fourcc(*"MJPG"),
                                                 self.config["fps"], size)
                    if not writer.isOpened():
                        raise OSError("OpenCV MJPG writer unavailable")
                if image.shape[1::-1] != size:
                    image = self.cv.resize(image, size)
                writer.write(image)
                if temporary.stat().st_size > self.config["max_clip_bytes"]:
                    raise OSError("Clip exceeded configured size")
            if writer is None:
                return None
            writer.release()
            writer = None
            if not 0 < temporary.stat().st_size <= self.config["max_clip_bytes"]:
                raise OSError("Clip is empty or exceeded configured size")
            os.replace(str(temporary), str(final))
            return filename
        finally:
            if writer is not None:
                writer.release()
            if temporary.exists():
                temporary.unlink()

    def _retention(self):
        files = sorted(((path.stat(), path) for path in self.root.glob("*.avi") if not path.name.endswith(".part.avi")),
                       key=lambda pair: pair[0].st_mtime, reverse=True)
        remaining, removed = 0, []
        oldest = time.time() - 86400 * self.config["retention_days"]
        for stat, path in files:
            remaining += stat.st_size
            if stat.st_mtime < oldest or remaining > self.config["max_total_bytes"]:
                path.unlink()
                remaining -= stat.st_size
                removed.append(path.name)
        return removed

    def _clean(self):
        try:
            return self._retention()
        except OSError:
            LOG.exception("Video retention failed")
            return []

    def _run(self):
        for path in self.root.glob("*.part.avi"):
            try:
                path.unlink()
            except OSError:
                LOG.warning("Could not clean partial clip %s", path)
        self._result([], None, self._clean())
        last_cleanup = time.monotonic()
        while not self.stop.is_set() or not self.jobs.empty():
            try:
                job = self.jobs.get(timeout=0.25)
            except Empty:
                if time.monotonic() - last_cleanup >= 60:
                    self._result([], None, self._clean())
                    last_cleanup = time.monotonic()
                continue
            filename = None
            try:
                filename = self._write(job)
            except (OSError, self.cv.error):
                LOG.exception("Clip write failed for event %s", job["ids"][0])
            removed = self._clean()
            self._result(job["ids"], filename if filename not in removed else None, removed)
            last_cleanup = time.monotonic()

    def drain(self):
        results = []
        while True:
            try:
                results.append(self.results.get_nowait())
            except Empty:
                return results

    def close(self):
        if self.pending:
            self._dispatch()
        self.stop.set()
        self.thread.join(8)
        if self.thread.is_alive():
            LOG.warning("Clip writer did not finish before shutdown")
