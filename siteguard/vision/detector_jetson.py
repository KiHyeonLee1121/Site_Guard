"""JetPack 4 native inference using jetson-inference and TensorRT."""

import os
from pathlib import Path
from time import perf_counter

from .detector_base import Detector, make_detection


class JetsonDetector(Detector):
    def __init__(self, config):
        try:
            import cv2
            import jetson_inference
            import jetson_utils
        except ImportError as error:
            raise RuntimeError("Jetson requires OpenCV and Python bindings for jetson-inference/jetson-utils") from error
        self.cv2, self.cuda = cv2, jetson_utils
        local = Path(config["model"] or "models/local/jetson").resolve()
        if not local.is_dir():
            raise ValueError("Prepare the offline SSD bundle with scripts/setup_model.sh jetson")
        network = local / "networks"
        files = [network / "models.json"] + [network / "SSD-Mobilenet-v2" / name
                                             for name in ("ssd_mobilenet_v2_coco.uff", "ssd_coco_labels.txt")]
        if not all(path.is_file() for path in files):
            raise ValueError("Expected SSD UFF weights and COCO labels under {}".format(local))
        argv = ["siteguard", "--network=siteguard-ssd-mobilenet-v2",
                "--threshold={}".format(config["confidence"]), "--batch-size=1"]
        # The native model registry resolves paths from cwd. Initialization precedes worker creation.
        previous = os.getcwd()
        try:
            os.chdir(str(local))
            self.net = jetson_inference.detectNet(argv=argv)
        finally:
            os.chdir(previous)
        self.names = {}
        for index in range(self.net.GetNumClasses()):
            name = self.net.GetClassDesc(index).strip().lower()
            if name in ("person", "dog"):
                if name in self.names.values():
                    raise ValueError("Duplicate class in Jetson label metadata")
                self.names[index] = name
        if set(self.names.values()) != {"person", "dog"}:
            raise ValueError("The Jetson model must provide COCO person and dog labels")
        self.confidence = config["confidence"]
        self.timing = {}

    def detect(self, frame):
        start = perf_counter()
        rgb = self.cv2.cvtColor(frame.image, self.cv2.COLOR_BGR2RGB)
        image = self.cuda.cudaFromNumpy(rgb, isBGR=False)
        prepared = perf_counter()
        raw = self.net.Detect(image, overlay="none")
        done = perf_counter()
        results = []
        for item in raw:
            detection = make_detection(frame, self.names.get(item.ClassID), item.Confidence,
                                       (item.Left, item.Top, item.Right, item.Bottom), self.confidence)
            if detection is not None:
                results.append(detection)
        self.timing = {"preprocess_ms": (prepared - start) * 1000, "inference_ms": (done - prepared) * 1000,
                       "postprocess_ms": (perf_counter() - done) * 1000}
        return results
