"""Ultralytics YOLO backend for a modern, isolated Python environment."""

from pathlib import Path

from .detector_base import Detector, class_ids, make_detection


class YoloDetector(Detector):
    def __init__(self, config):
        if not config["model"] or not Path(config["model"]).is_file():
            raise ValueError("YOLO weights are missing. Prepare a local .pt file and specify --model.")
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Install the isolated development YOLO dependencies") from error
        self.model = YOLO(config["model"], task="detect")
        self.names = class_ids(self.model.names)
        self.config = config
        self.timing = {}

    def detect(self, frame):
        result = self.model.predict(frame.image, imgsz=self.config["input_size"],
                                    device=self.config["device"], conf=self.config["confidence"],
                                    classes=list(self.names), verbose=False)[0]
        self.timing = {key + "_ms": float(value) for key, value in result.speed.items() if value is not None}
        boxes = result.boxes.data.detach().cpu().tolist()
        detections = []
        for x1, y1, x2, y2, conf, idx in boxes:
            detection = make_detection(frame, self.names.get(int(idx)), conf, (x1, y1, x2, y2),
                                       self.config["confidence"])
            if detection is not None:
                detections.append(detection)
        return detections
