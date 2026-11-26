"""Virtual-time fixtures, video playback, and latest-frame camera acquisition."""

import logging
import math
from pathlib import Path
from threading import Condition, Event, Thread
import time

from siteguard.schemas import Frame

LOG = logging.getLogger("siteguard.vision")
SCENARIOS = ("tour", "roi1", "roi2", "critical", "dog", "multi", "dropout")


def fixture(name, x, y=0.79):
    return name, 0.94, (x - 0.065, y - 0.26, x + 0.065, y)


def scenario_at(scenario, t):
    if scenario == "tour":
        if t < 3:
            return scenario_at("roi1", t)
        if t < 16:
            return scenario_at("roi2", t - 3)
        if t < 22:
            return scenario_at("critical", t - 16)
        return scenario_at("dog", t - 22)
    if scenario == "roi1" and 0.5 <= t < 2:
        return [fixture("person", 0.1 + t * 0.07)]
    if scenario in ("roi2", "dog", "dropout") and 0.5 <= t < 10.5:
        if scenario == "dropout" and (6.2 <= t < 6.5 or t >= 7):
            return []
        x = 0.50 if t < 7.5 else max(0.14, 0.50 - (t - 7.5) * 0.35)
        return [fixture("dog" if scenario == "dog" else "person", x)]
    if scenario == "critical" and 0.5 <= t < 5.95:
        x = max(0.18, 0.78 - max(0, t - 2.6) * 0.34)
        return [fixture("person", x)]
    if scenario == "multi" and 0.5 <= t < 9:
        objects = [fixture("person", 0.50)]
        return objects + ([fixture("dog", 0.80, 0.88)] if t >= 6 else [])
    return []


class MockSource:
    def __init__(self, config, scenario, realtime, inputs=None):
        self.config, self.scenario, self.realtime, self.inputs = config, scenario, realtime, inputs

    def frames(self, stop):
        start = time.monotonic()
        fps = self.config["fps"]
        length = 36 if self.scenario == "tour" else 12
        rows = self.inputs if self.inputs is not None else (
            (i / fps, scenario_at(self.scenario, i / fps)) for i in range(length * fps)
        )
        for t, objects in rows:
            if stop.is_set() or (self.realtime and stop.wait(max(0, start + t - time.monotonic()))):
                return
            yield Frame(None, self.config["width"], self.config["height"], t, None, objects)


def open_cv():
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required for camera/video input and event clips") from error
    return cv2


class VideoSource:
    def __init__(self, path, realtime):
        if not path or not Path(path).is_file():
            raise ValueError("Provide a readable video file with --video")
        self.path, self.realtime = path, realtime
        self.fps = None

    def frames(self, stop):
        cv2 = open_cv()
        cap = cv2.VideoCapture(self.path)
        try:
            if not cap.isOpened():
                raise RuntimeError("Unable to open video: " + self.path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                fps = 25.0
                LOG.warning("Video FPS unavailable; assuming 25 FPS for missing timestamps")
            self.fps = fps
            start, last, first, count = time.monotonic(), None, None, 0
            while not stop.is_set():
                ok, image = cap.read()
                if not ok:
                    if count == 0:
                        raise RuntimeError("Video opened but yielded no decodable frames: " + self.path)
                    return
                position = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                if math.isfinite(position) and position >= 0 and first is None:
                    first = position if last is None else position - (last + 1 / fps)
                candidate = position - first if first is not None and math.isfinite(position) else -1
                timestamp = candidate if candidate >= 0 and (last is None or candidate > last) else (
                    0.0 if last is None else last + 1 / fps
                )
                if self.realtime and stop.wait(max(0, start + timestamp - time.monotonic())):
                    return
                h, w = image.shape[:2]
                yield Frame(image, w, h, timestamp, None, None)
                last, count = timestamp, count + 1
        finally:
            cap.release()


class LatestCamera:
    def __init__(self, config):
        self.config = config
        self.cv2 = open_cv()
        self.ready = Condition()
        self.shutdown = Event()
        self.latest = None
        self.version = self.dropped = self.read_version = 0
        self.status = "connecting"
        self.thread = Thread(target=self._capture, daemon=True, name="camera-capture")

    def _capture(self):
        c, cv = self.config, self.cv2
        while not self.shutdown.is_set():
            LOG.info("Opening camera %s", c["gstreamer"] or c["camera_index"])
            self.status = "connecting"
            cap = None
            try:
                if c["gstreamer"]:
                    cap = cv.VideoCapture(c["gstreamer"], cv.CAP_GSTREAMER)
                else:
                    cap = cv.VideoCapture(c["camera_index"], cv.CAP_V4L2) if hasattr(cv, "CAP_V4L2") else cv.VideoCapture(c["camera_index"])
                    if not cap.isOpened():
                        cap.release()
                        cap = cv.VideoCapture(c["camera_index"])
                    for prop, key in ((cv.CAP_PROP_FRAME_WIDTH, "width"), (cv.CAP_PROP_FRAME_HEIGHT, "height"),
                                      (cv.CAP_PROP_FPS, "fps")):
                        cap.set(prop, c[key])
                if not cap.isOpened():
                    raise RuntimeError("Camera open failed. Check device path and permissions.")
                while not self.shutdown.is_set():
                    began = time.monotonic()
                    ok, image = cap.read()
                    now = time.monotonic()
                    if not ok:
                        raise RuntimeError("Camera frame read failed")
                    h, w = image.shape[:2]
                    frame = Frame(image, w, h, now, began, None)
                    self.status = "capturing"
                    with self.ready:
                        if self.read_version != self.version:
                            self.dropped += 1
                        self.version += 1
                        self.latest = frame
                        self.ready.notify()
            except (RuntimeError, self.cv2.error) as error:
                self.status = "disconnected"
                LOG.warning("%s Retrying in %.1fs", error, c["reconnect_sec"])
            finally:
                if cap is not None:
                    cap.release()
            self.shutdown.wait(c["reconnect_sec"])

    def frames(self, stop):
        self.thread.start()
        try:
            while not stop.is_set():
                with self.ready:
                    self.ready.wait_for(lambda: self.read_version != self.version, timeout=0.25)
                    frame = self.latest if self.read_version != self.version else None
                    self.read_version = self.version
                yield frame
        finally:
            self.shutdown.set()
            self.thread.join(timeout=1)
