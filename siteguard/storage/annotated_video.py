"""Export the analyzed source frames and their SiteGuard decisions."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from siteguard.engine.roi_manager import ROIManager
from siteguard.vision.sources import open_cv


COLORS = {0: (230, 230, 230), 1: (90, 230, 90), 2: (30, 215, 255), 3: (55, 75, 255)}


class AnnotatedVideo:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.suffix.lower() != ".mp4":
            raise ValueError("--output-video must be a new .mp4 file")
        if self.path.exists() or self.path.is_symlink():
            raise ValueError("Output already exists: {}".format(self.path))
        self.cv = open_cv()
        self.writer = None
        self.size = None
        self.cleared_until = 0.0

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.temp = TemporaryDirectory(prefix=".siteguard-", dir=str(self.path.parent))
        self.staged = Path(self.temp.name) / "annotated.mp4"
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.writer is not None:
                self.writer.release()
        finally:
            self.temp.cleanup()

    def finish(self):
        if self.writer is None:
            raise RuntimeError("No frames were available for the annotated video")
        self.writer.release()
        self.writer = None
        if self.staged.stat().st_size == 0:
            raise RuntimeError("OpenCV did not write the annotated video")
        os.link(str(self.staged), str(self.path))

    def write(self, frame, fps, zones, observations, statuses, events, output):
        cv = self.cv
        w, h = frame.width, frame.height
        if self.writer is None:
            self.size = (w, h)
            # OpenCV can silently crop the last row or column when encoding odd sizes.
            encoded_size = (w + w % 2, h + h % 2)
            self.writer = cv.VideoWriter(str(self.staged), cv.VideoWriter_fourcc(*"mp4v"), fps, encoded_size)
            if not self.writer.isOpened():
                raise RuntimeError("OpenCV could not open the MP4 video encoder")
        if (w, h) != self.size:
            raise ValueError("Annotated video requires a constant input frame size")

        image = cv.copyMakeBorder(frame.image, 0, h % 2, 0, w % 2, cv.BORDER_CONSTANT)
        scale = max(0.30, min(1.1, w / 1000))
        weight = max(1, round(w / 640))
        for zone in zones:
            color = COLORS[zone["level"]]
            points = [(min(w - 1, round(x * w)), min(h - 1, round(y * h))) for x, y in zone["points"]]
            for i, point in enumerate(points):
                cv.line(image, points[i - 1], point, color, weight, cv.LINE_AA)
            self._label(image, "ROI {}".format(zone["level"]), *points[0], color, scale * 0.8, weight)

        by_id = {status.track_id: status for status in statuses}
        for obs in observations:
            status = by_id[obs.track_id]
            det = obs.detection
            x1, y1, x2, y2 = map(round, det.bbox)
            color = COLORS[status.roi]
            cv.rectangle(image, (x1, y1), (x2, y2), color, weight)
            foot_x, foot_y = ROIManager.foot_point(det.bbox, w, h)
            cv.circle(image, (round(foot_x * w), round(foot_y * h)), weight * 3, color, -1, cv.LINE_AA)
            zone_label = "ROI {}".format(status.roi) if status.roi else "OUTSIDE"
            if status.roi == 2:
                zone_label += " {:.1f}s".format(status.dwell)
            category = "PERSON" if det.class_name == "person" else "ANIMAL (DOG)"
            label = "{} #{} | {}".format(category, obs.track_id, zone_label)
            self._label(image, label, x1, y1 - 6, color, scale * 0.8, weight)

        if not output.level and any(event.kind == "cleared" for event in events):
            self.cleared_until = frame.timestamp + 1.5
        if output.level:
            self.cleared_until = 0.0
            color = COLORS[output.level + 1]
            selected = by_id[output.sound_revision[0]]
            if selected.state == "CLEARING":
                message = "ALERT CLEARING"
            elif output.level == 2:
                message = "CRITICAL - PROTECTED AREA ENTRY"
            else:
                message = "WARNING - ROI 2 DWELL"
        elif frame.timestamp < self.cleared_until:
            message, color = "ALERT CLEARED", COLORS[1]
        else:
            message, color = "MONITORING", COLORS[0]
        self._label(image, message, 8, h - 10, color, scale, weight)
        self.writer.write(image)

    def _label(self, image, label, x, y, color, scale, weight):
        cv = self.cv
        font = cv.FONT_HERSHEY_SIMPLEX
        (width, height), baseline = cv.getTextSize(label, font, scale, weight)
        h, w = image.shape[:2]
        x = max(4, min(x, w - width - 5))
        y = min(h - 1, max(height + 5, y))
        cv.rectangle(image, (x - 4, y - height - 4), (x + width + 4, y + baseline), (23, 23, 23), -1)
        cv.putText(image, label, (x, y), font, scale, color, weight, cv.LINE_AA)
