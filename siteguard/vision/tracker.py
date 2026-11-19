"""Class-aware short-term tracking with IoU, velocity and a center gate."""

from math import hypot

from siteguard.schemas import Observation


def iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    total = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / total if total > 0 else 0.0


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


class Track:
    def __init__(self, detection):
        self.detection = detection
        self.velocity = (0.0, 0.0)

    def predict(self, now):
        elapsed = min(0.5, max(0, now - self.detection.timestamp))
        return tuple(value + self.velocity[i % 2] * elapsed for i, value in enumerate(self.detection.bbox))

    def update(self, detection):
        elapsed = detection.timestamp - self.detection.timestamp
        if elapsed >= 0.02:
            before, after = center(self.detection.bbox), center(detection.bbox)
            self.velocity = tuple((after[i] - before[i]) / elapsed for i in (0, 1))
        self.detection = detection


class Tracker:
    def __init__(self, config):
        self.config = config
        self.tracks = {}
        self.next_id = 1
        self.size = None

    def update(self, detections, now, width, height):
        dimensions = (width, height)
        expired = [key for key, track in self.tracks.items()
                   if self.size != dimensions or now - track.detection.timestamp >= self.config["ttl"]]
        self.size = dimensions
        for key in expired:
            del self.tracks[key]
        candidates = []
        detections = sorted(detections, key=lambda d: -d.confidence)[:self.config["max_tracks"]]
        diagonal = hypot(width, height)
        for key, track in self.tracks.items():
            predicted = track.predict(now)
            for index, detection in enumerate(detections):
                if detection.class_name != track.detection.class_name:
                    continue
                overlap = iou(predicted, detection.bbox)
                a, b = center(predicted), center(detection.bbox)
                distance = hypot(a[0] - b[0], a[1] - b[1]) / diagonal
                gate = self.config["center_gate"]
                if overlap >= self.config["min_iou"] or distance <= gate:
                    candidates.append((-(overlap + max(0, 1 - distance / gate) * 0.5), key, index))
        matched_tracks, matched_detections = set(), set()
        for _, key, index in sorted(candidates):
            if key not in matched_tracks and index not in matched_detections:
                self.tracks[key].update(detections[index])
                matched_tracks.add(key)
                matched_detections.add(index)
        for index, detection in enumerate(detections):
            if index not in matched_detections and len(self.tracks) < self.config["max_tracks"]:
                self.tracks[self.next_id] = Track(detection)
                matched_tracks.add(self.next_id)
                self.next_id += 1
        return [Observation(key, track.detection, key in matched_tracks)
                for key, track in self.tracks.items()], expired
