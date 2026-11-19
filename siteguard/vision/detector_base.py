"""Common detector API and normalization of model output."""

import math
from abc import ABC, abstractmethod

from siteguard.schemas import Detection

CLASSES = {"person", "dog"}


class Detector(ABC):
    @abstractmethod
    def detect(self, frame):
        """Return normalized Detection records for this frame."""


def class_ids(names):
    items = names.items() if isinstance(names, dict) else enumerate(names)
    result = {int(index): str(name).strip().lower() for index, name in items
              if str(name).strip().lower() in CLASSES}
    if len(result) != len(CLASSES) or set(result.values()) != CLASSES:
        raise ValueError("Model labels must contain exactly one person and one dog class")
    return result


def make_detection(frame, name, confidence, bbox, threshold):
    if name not in CLASSES or not threshold <= confidence <= 1 or not all(math.isfinite(x) for x in bbox):
        return None
    x1, y1, x2, y2 = (max(0.0, min(bound, float(value)))
                      for value, bound in zip(bbox, (frame.width, frame.height) * 2))
    if x2 > x1 and y2 > y1:
        return Detection(name, float(confidence), (x1, y1, x2, y2), frame.timestamp)
    return None
