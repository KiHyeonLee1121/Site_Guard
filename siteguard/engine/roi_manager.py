"""Normalized polygon geometry and thread-safe, atomic ROI configuration."""

import json
import os
import tempfile
from pathlib import Path
from threading import Lock

EPSILON = 1e-9


def cross(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def on_segment(a, b, p):
    return abs(cross(a, b, p)) < EPSILON and all(
        min(a[i], b[i]) - EPSILON <= p[i] <= max(a[i], b[i]) + EPSILON for i in (0, 1)
    )


def intersects(a, b, c, d):
    if any(on_segment(x, y, z) for x, y, z in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))):
        return True
    return cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0


def contains(polygon, point):
    x, y = point
    inside = False
    for index, b in enumerate(polygon):
        a = polygon[index - 1]
        if on_segment(a, b, point):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def validate_zones(payload):
    zones = payload.get("zones") if isinstance(payload, dict) else None
    if not isinstance(zones, list) or len(zones) > 3:
        raise ValueError("zones must be a list of up to three polygons")
    result = {}
    for zone in zones:
        if not isinstance(zone, dict):
            raise ValueError("Invalid polygon object")
        level, name, points = (zone.get(key) for key in ("level", "name", "points"))
        if type(level) is not int or level not in (1, 2, 3) or level in result:
            raise ValueError("Use one polygon per ROI level (1, 2, 3)")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("ROI names must have 1–80 characters")
        if not isinstance(points, list) or not 3 <= len(points) <= 64:
            raise ValueError("Each polygon requires 3–64 points")
        vertices = []
        for point in points:
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in point)):
                raise ValueError("Polygon coordinates must be finite and normalized")
            vertices.append(tuple(point))
        if len(set(vertices)) != len(vertices) or abs(sum(
            cross((0, 0), vertices[i - 1], p) for i, p in enumerate(vertices)
        )) < EPSILON:
            raise ValueError("Polygon needs distinct vertices and nonzero area")
        edges = list(zip(vertices, vertices[1:] + vertices[:1]))
        for i, (a, b) in enumerate(edges):
            for j in range(i + 2, len(edges)):
                if not (i == 0 and j == len(edges) - 1) and intersects(a, b, *edges[j]):
                    raise ValueError("Polygon edges must not intersect")
            if on_segment(a, b, edges[(i + 1) % len(edges)][1]):
                raise ValueError("Adjacent edges must not overlap")
        result[level] = {"level": level, "name": name.strip(), "points": vertices}
    return {"zones": [result[i] for i in sorted(result)]}


class ROIManager:
    def __init__(self, path, example, require_calibration=False):
        self.path = Path(path)
        self.example = Path(example)
        self.lock = Lock()
        self.using_example = not self.path.exists()
        if self.using_example and require_calibration:
            raise ValueError("ROI calibration missing: {}. Save the actual tape polygons with the dashboard first."
                             .format(self.path))
        source = self.example if self.using_example else self.path
        self.payload = validate_zones(json.loads(source.read_text(encoding="utf-8")))
        if require_calibration and not self.payload["zones"]:
            raise ValueError("ROI calibration has no zones: {}".format(self.path))
        self.revision = 0

    def snapshot(self):
        with self.lock:
            return self.revision, self.payload

    def save(self, payload, expected=None):
        validated = validate_zones(payload)
        with self.lock:
            if expected is not None and expected != self.revision:
                raise ValueError("ROI settings changed. Reload before saving.")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".roi-", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(validated, handle, indent=2, ensure_ascii=False, allow_nan=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, str(self.path))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self.payload = validated
            self.using_example = False
            self.revision += 1
            return self.revision

    @staticmethod
    def foot_point(bbox, width, height):
        x1, _, x2, y2 = bbox
        return ((x1 + x2) / (2 * width), y2 / height)

    @staticmethod
    def classify(payload, bbox, width, height):
        point = ROIManager.foot_point(bbox, width, height)
        return max((z["level"] for z in payload["zones"] if contains(z["points"], point)), default=0)
