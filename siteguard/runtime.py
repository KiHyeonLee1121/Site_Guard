"""Run the local engine and manage its background adapters."""

from collections import defaultdict, deque
from contextlib import ExitStack
from logging.handlers import RotatingFileHandler
import logging
import os
from pathlib import Path
import sqlite3
import time

from siteguard.config import EXAMPLE_ROI
from siteguard.dashboard.server import Dashboard, DashboardState
from siteguard.engine.controller import ActionController
from siteguard.engine.roi_manager import ROIManager
from siteguard.hardware.mock_hardware import MockActuator
from siteguard.hardware.pir_manager import PIR
from siteguard.network.cloud_client import HttpCloud
from siteguard.network.event_sync import EventSync
from siteguard.pipeline import Pipeline
from siteguard.schemas import OFF
from siteguard.storage.database import Database
from siteguard.storage.event_logger import EventLogger
from siteguard.vision.detector_mock import MockDetector
from siteguard.vision.frame_manager import FrameGate
from siteguard.vision.sources import LatestCamera, MockSource, VideoSource, open_cv
from siteguard.vision.tracker import Tracker

LOG = logging.getLogger("siteguard.runtime")


def configure_logging(path, debug):
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as error:
            LOG.warning("Log file unavailable; still logging to stderr: %s", error)


def make_source(config, args):
    source = config["source"]
    if source["kind"] == "camera":
        return LatestCamera(source)
    if source["kind"] == "video":
        return VideoSource(args.video, args.realtime or config["serial"]["enabled"])
    return MockSource(source, args.scenario, args.realtime)


def make_detector(config):
    kind = config["backend"]
    if kind == "jetson":
        from siteguard.vision.detector_jetson import JetsonDetector
        return JetsonDetector(config)
    if kind == "yolo":
        from siteguard.vision.detector_yolo import YoloDetector
        return YoloDetector(config)
    if kind == "tensorrt":
        from siteguard.vision.detector_tensorrt import TensorRTDetector
        return TensorRTDetector(config)
    return MockDetector(config["confidence"])


class Metrics:
    def __init__(self):
        self.series = defaultdict(lambda: deque(maxlen=512))
        self.frames = self.skipped = self.detection_count = 0
        self.classes = set()
        self.started = time.monotonic()

    def add(self, values):
        for key, value in values.items():
            self.series[key].append(value)

    def snapshot(self):
        seconds = time.monotonic() - self.started
        result = {}
        for key, values in self.series.items():
            ordered = sorted(values)
            p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            result[key] = {"mean": round(sum(ordered) / len(ordered), 3), "p95": round(p95, 3),
                           "samples": len(ordered)}
        return {"frames": self.frames, "rate_skips": self.skipped, "detections": self.detection_count,
                "detected_classes": sorted(self.classes),
                "wall_s": round(seconds, 3), "processing_fps": round(self.frames / max(seconds, 0.001), 2),
                "latency_ms": result}


class Engine:
    def __init__(self, config, args, stop, source, pipeline, actuator, events, dashboard, cloud, recorder,
                 annotated_video=None):
        self.config, self.args, self.stop = config, args, stop
        self.source, self.pipeline, self.actuator = source, pipeline, actuator
        self.events, self.dashboard, self.cloud, self.recorder = events, dashboard, cloud, recorder
        self.annotated_video = annotated_video
        self.camera = config["source"]["kind"] == "camera"
        self.metrics = Metrics()
        self.pir = PIR(config["pir"])
        self.gate = FrameGate(config["vision"]["idle_hz"], config["vision"]["active_hz"])
        self.last_capture = self.last_housekeeping = time.monotonic()
        self.last_status = None
        self.last_board = float("-inf")
        self.stale = False
        self.image_sequence = 0
        self.objects = []
        self.width = self.height = None
        self.event_counts = defaultdict(int)

    def record(self, kind, now, **fields):
        self.event_counts[kind] += 1
        return self.events.write(kind, now, **fields)

    def collect_results(self):
        for result in self.actuator.drain():
            if result.get("serial_ms") is not None and self.actuator.status["connection"] != "mock":
                self.metrics.add({"serial_ack_ms": result["serial_ms"]})
            self.events.update("save_response", result)
        if self.recorder:
            for ids, filename, removed in self.recorder.drain():
                if ids:
                    self.events.update("save_clip", ids, filename)
                if removed:
                    self.events.update("forget_clips", removed)

    def publish(self, frame=None, final=False):
        if not self.config["dashboard"]["enabled"]:
            return
        now = time.monotonic()
        if not final and now - self.last_board < 1 / self.config["dashboard"]["preview_hz"]:
            return
        self.last_board = now
        jpeg = None
        if frame is not None and frame.image is not None:
            cv2 = open_cv()
            width = min(frame.width, self.config["dashboard"]["preview_width"])
            image = frame.image
            if width != frame.width:
                height = max(1, round(width * frame.height / frame.width))
                image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if ok:
                jpeg = encoded.tobytes()
                self.image_sequence += 1
        has_image = bool(jpeg or self.dashboard.snapshot()[1]) and not self.stale
        try:
            queued = self.events.database.queue_state()
        except sqlite3.Error:
            queued = None
        self.dashboard.update({
            "running": not final, "has_image": has_image, "image_sequence": self.image_sequence,
            "input_status": "stale" if self.stale else getattr(self.source, "status", "processing"),
            "width": self.width, "height": self.height, "objects": self.objects,
            "output": self.pipeline.controller.current._asdict(), "hardware": self.actuator.status,
            "cloud": self.cloud.status, "queued": queued, "storage_errors": self.events.errors,
            "roi_revision": self.pipeline.roi.snapshot()[0]
        }, jpeg, clear_image=self.stale)

    def reset(self, now, reason):
        transitions, command = self.pipeline.reset()
        self.objects = []
        for event in transitions:
            self.record(event.kind, now, track=event.status, output=OFF, command=command, detail=reason)
        if command is not None:
            self.record("output", now, output=OFF, command=command, detail=reason)

    def _maintenance(self, now):
        self.collect_results()
        pir_value = self.actuator.status["pir"]
        kind = self.pir.update(pir_value, now)
        if kind:
            self.record(kind, now)
        if now - self.last_housekeeping >= 60:
            storage = self.config["storage"]
            self.events.update("prune", time.time() - storage["retention_days"] * 86400, storage["max_events"])
            self.last_housekeeping = now
            LOG.info("Runtime metrics %s", self.metrics.snapshot())

    def step(self, frame):
        now = time.monotonic()
        self._maintenance(now)
        if frame is None:
            if now - self.last_capture >= self.config["source"]["stale_sec"] and not self.stale:
                self.stale = True
                self.reset(now, "camera_stale")
                self.record("camera_stale", now)
                LOG.warning("Camera input stale. Resetting active warnings.")
            self.publish()
            return
        if self.camera:
            self.last_capture = frame.timestamp
            if self.stale:
                self.record("camera_recovered", frame.timestamp)
                self.gate.last = None
                self.stale = False
        if self.recorder is not None:
            try:
                self.recorder.observe(frame)
            except self.recorder.cv.error as error:
                LOG.warning("Unable to buffer event frame: %s", error)
        if self.camera and not self.gate.allow(frame.timestamp, bool(self.pipeline.states) or self.pir.boosted(now)):
            self.metrics.skipped += 1
            return
        observations, statuses, transitions, output, command, timing = self.pipeline.step(frame)
        if hasattr(self.actuator, "touch"):
            self.actuator.touch()
        self.width, self.height = frame.width, frame.height
        self.metrics.frames += 1
        self.last_status = frame.timestamp
        if frame.captured_at is not None:
            timing["capture_read_ms"] = 1000 * (frame.timestamp - frame.captured_at)
            timing["capture_to_decision_ms"] = 1000 * (time.monotonic() - frame.timestamp)
        self.metrics.add(timing)
        visible = [obs for obs in observations if obs.visible]
        self.metrics.detection_count += len(visible)
        self.metrics.classes.update(obs.detection.class_name for obs in visible)

        clips = []
        for event in transitions:
            clip = self.recorder is not None and event.kind in ("warning", "critical")
            identifier = self.record(event.kind, frame.timestamp, track=event.status,
                                     output=output, command=command, clip=clip)
            if clip and identifier:
                clips.append(identifier)
        if self.recorder is not None:
            self.recorder.mark(clips, frame.timestamp)
        if command is not None:
            self.record("output", frame.timestamp, output=output, command=command)
        if self.annotated_video is not None:
            self.annotated_video.write(frame, self.source.fps, self.pipeline.roi_zones,
                                       visible, statuses, transitions, output)
        if self.config["dashboard"]["enabled"]:
            statuses = {status.track_id: status for status in statuses}
            self.objects = [dict(id=obs.track_id, bbox=obs.detection.bbox, class_name=obs.detection.class_name,
                                 confidence=obs.detection.confidence, visible=obs.visible,
                                 roi=statuses[obs.track_id].roi, dwell=statuses[obs.track_id].dwell,
                                 state=statuses[obs.track_id].state)
                            for obs in observations if obs.track_id in statuses]
            self.publish(frame)

    def run(self):
        storage = self.config["storage"]
        self.events.update("prune", time.time() - storage["retention_days"] * 86400, storage["max_events"])
        frames = self.source.frames(self.stop)
        try:
            for frame in frames:
                if self.stop.is_set():
                    break
                self.step(frame)
                if self.args.max_frames and self.metrics.frames >= self.args.max_frames:
                    break
        finally:
            frames.close()
            try:
                self.reset(self.last_status, "shutdown")
            finally:
                self.actuator.close()
                if self.recorder is not None:
                    self.recorder.close()
                self.collect_results()
                self.publish(final=True)
        return dict(self.metrics.snapshot(), source=self.config["source"]["kind"],
                    backend=self.config["vision"]["backend"], camera_drops=getattr(self.source, "dropped", 0),
                    events=dict(self.event_counts), storage_errors=self.events.errors)


def run(config, args, stop):
    source_kind = config["source"]["kind"]
    with ExitStack() as resources:
        roi = ROIManager(config["roi_file"], EXAMPLE_ROI,
                         require_calibration=bool(args.output_video or config["serial"]["enabled"]))
        if roi.using_example and source_kind != "mock":
            LOG.warning("Using example ROI coordinates. Calibrate the actual tape boundaries and save %s.",
                        config["roi_file"])
        source = make_source(config, args)
        annotated_video = None
        if args.output_video:
            from siteguard.storage.annotated_video import AnnotatedVideo
            annotated_video = resources.enter_context(AnnotatedVideo(args.output_video))
        detector = make_detector(config["vision"])
        if hasattr(detector, "close"):
            resources.callback(detector.close)
        database = Database(config["storage"]["database"])
        resources.callback(database.close)
        sync_config = config["cloud"]
        url = os.getenv("SITEGUARD_CLOUD_URL") or sync_config["url"]
        client = HttpCloud(url, os.getenv("SITEGUARD_CLOUD_TOKEN", ""), sync_config["timeout"]) if url and sync_config["enabled"] else None
        cloud = EventSync(database, client, sync_config)
        if sync_config["enabled"]:
            cloud.start()
            resources.callback(cloud.close)
        else:
            cloud.status = "disabled"
        events = EventLogger(database, source_kind, sync_config["enabled"])
        dashboard_state = DashboardState({"source": source_kind, "backend": config["vision"]["backend"],
                                          "running": True, "has_image": False, "objects": []})
        if config["dashboard"]["enabled"]:
            dashboard = Dashboard(config["dashboard"], os.getenv("SITEGUARD_DASHBOARD_TOKEN", ""),
                                  dashboard_state, roi, database, config["policy"])
            resources.callback(dashboard.close)
            LOG.info("Dashboard listening at http://%s:%s", *dashboard.http.server_address)
        recorder = None
        if config["recording"]["enabled"] and source_kind != "mock":
            from siteguard.storage.video_recorder import VideoRecorder
            try:
                recorder = VideoRecorder(config["recording"])
                resources.callback(recorder.close)
            except OSError:
                LOG.exception("Recording directory unavailable; continuing with event metadata")
        if config["serial"]["enabled"]:
            from siteguard.hardware.arduino_serial import SerialActuator
            actuator = SerialActuator(config["serial"], max(3.0, config["source"]["stale_sec"]))
            resources.callback(actuator.close)
        else:
            actuator = MockActuator()
        pipeline = Pipeline(detector, Tracker(config["tracker"]), roi, config["policy"], ActionController(actuator))
        engine = Engine(config, args, stop, source, pipeline, actuator, events, dashboard_state, cloud, recorder,
                        annotated_video)
        result = engine.run()
        if annotated_video is not None and not stop.is_set():
            annotated_video.finish()
            LOG.info("Annotated video written to %s", annotated_video.path)
        if args.stay_open and config["dashboard"]["enabled"] and not stop.is_set():
            LOG.info("Analysis complete. Dashboard remains open until interrupted.")
            while not stop.wait(0.5):
                engine.publish(final=True)
        return result
