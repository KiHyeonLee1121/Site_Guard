"""Deterministic, configurable fixtures use normal detector contracts."""

from .detector_base import Detector, make_detection


class MockDetector(Detector):
    def __init__(self, confidence):
        self.confidence = confidence

    def detect(self, frame):
        detections = []
        for name, conf, normalized_box in frame.fixture:
            bbox = [value * scale for value, scale in zip(normalized_box, (frame.width, frame.height) * 2)]
            detection = make_detection(frame, name, conf, bbox, self.confidence)
            if detection is not None:
                detections.append(detection)
        return detections
