import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from siteguard.config import load
from siteguard.main import config_for, parse
from siteguard.runtime import run
from siteguard.schemas import Detection, Frame
from siteguard.storage.video_recorder import VideoRecorder
from siteguard.vision.detector_tensorrt import decode, letterbox
from siteguard.vision.sources import VideoSource

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, "Optional OpenCV and NumPy required")
class VideoTests(unittest.TestCase):
    def test_annotated_classroom_video_uses_policy_and_preserves_input_frames(self):
        with TemporaryDirectory() as directory:
            source, output, roi = (Path(directory, name) for name in ("input.avi", "output.mp4", "roi.json"))
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (320, 240))
            self.assertTrue(writer.isOpened())
            try:
                for _ in range(70):
                    writer.write(np.full((240, 320, 3), 110, dtype=np.uint8))
            finally:
                writer.release()
            original = source.read_bytes()
            args = parse(["--video", str(source), "--roi-file", str(roi), "--output-video", str(output),
                          "--database", str(Path(directory, "events.sqlite3")), "--dry-run"])
            config = config_for(args)
            with self.assertRaisesRegex(ValueError, "ROI calibration missing"):
                run(config, args, Event())
            self.assertFalse(output.exists())
            zones = [
                {"level": level, "name": "Tape {}".format(level),
                 "points": [(left, 0.5), (right, 0.5), (right, 0.95), (left, 0.95)]}
                for level, left, right in [(1, 0, 0.3), (2, 0.3, 0.65), (3, 0.65, 1)]
            ]
            roi.write_text(json.dumps({"zones": zones}), encoding="utf-8")

            class WalkingDetector:
                def detect(self, frame):
                    t = frame.timestamp
                    if t < 3:
                        x = min(135, 56 + 35 * t)
                    elif t < 8:
                        x = 135
                    elif t < 10:
                        x = min(230, 135 + 60 * (t - 8))
                    else:
                        x = max(65, 230 - 100 * (t - 10))
                    return [Detection("person", 0.95, (x - 20, 60, x + 20, 190), t)]

            with patch("siteguard.runtime.make_detector", return_value=WalkingDetector()):
                result = run(config, args, Event())
            self.assertEqual(result["frames"], 70)
            self.assertEqual(result["events"].get("warning"), 1)
            self.assertEqual(result["events"].get("critical"), 1)
            self.assertEqual(result["events"].get("cleared"), 1)
            self.assertEqual(source.read_bytes(), original)
            frames = list(VideoSource(str(output), False).frames(Event()))
            self.assertEqual(len(frames), 70)
            self.assertAlmostEqual(frames[-1].timestamp, 13.8)
            self.assertEqual((frames[0].width, frames[0].height), (320, 240))
            self.assertAlmostEqual(float(frames[0].image[35, 30].mean()), 110, delta=10)
            # The lower subtitle changes from neutral to yellow for ROI 2 and red for ROI 3.
            yellow = frames[36].image[221:232, 8:160].astype(int)
            red = frames[49].image[221:232, 8:160].astype(int)
            self.assertGreater(int((yellow[:, :, 1] - yellow[:, :, 0]).max()), 75)
            self.assertGreater(int((red[:, :, 2] - red[:, :, 1]).max()), 100)
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                run(config, args, Event())

    def test_video_timestamps_and_dimensions(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory, "input.avi"))
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (64, 48))
            self.assertTrue(writer.isOpened())
            for i in range(7):
                writer.write(np.full((48, 64, 3), i * 15, dtype=np.uint8))
            writer.release()
            frames = list(VideoSource(path, False).frames(Event()))
            self.assertEqual(len(frames), 7)
            self.assertEqual((frames[0].width, frames[0].height), (64, 48))
            self.assertAlmostEqual(frames[-1].timestamp, 1.2)

    def test_letterbox_decode_nms_and_other_classes(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        padded, transform = letterbox(cv2, image, 320, 320)
        self.assertEqual(padded.shape, (320, 320, 3))
        frame = Frame(image, 200, 100, 0.4, None, None)
        predictions = np.array([[160, 160, 160], [160, 160, 160], [80, 80, 80], [80, 80, 80],
                                [0.9, 0.8, 0.65], [0.1, 0.1, 0.1], [0.1, 0.1, 0.99]], dtype=float)
        result = decode(cv2, np, frame, predictions, {0: "person", 1: "dog"}, 0.45, transform)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].bbox, (75, 25, 125, 75))
        self.assertEqual(result[0].timestamp, 0.4)

    def test_event_clip_includes_buffer_and_postroll(self):
        with TemporaryDirectory() as directory:
            config = dict(load()["recording"], directory=directory, fps=5, pre_sec=0.6, post_sec=0.6)
            recorder = VideoRecorder(config)
            try:
                for i in range(11):
                    frame = Frame(np.full((48, 64, 3), i * 15, dtype=np.uint8), 64, 48, i / 5, None, None)
                    recorder.observe(frame)
                    if i == 4:
                        recorder.mark(["event-a"], frame.timestamp)
            finally:
                recorder.close()
            result = next(item for item in recorder.drain() if item[0] == ["event-a"])
            self.assertEqual(result[1], "event-a.avi")
            frames = list(VideoSource(str(Path(directory, result[1])), False).frames(Event()))
            self.assertGreaterEqual(len(frames), 6)
            self.assertLess(float(frames[0].image.mean()), 60)
            self.assertGreater(float(frames[-1].image.mean()), 60)
