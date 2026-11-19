from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from siteguard.config import load
from siteguard.schemas import Frame
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
