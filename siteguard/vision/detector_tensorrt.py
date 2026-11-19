"""TensorRT 8 fixed-batch raw YOLO11 adapter. Load only on demand."""

import json
from pathlib import Path
from time import perf_counter
import math

from .detector_base import Detector, class_ids, make_detection


def letterbox(cv2, image, height, width):
    image_height, image_width = image.shape[:2]
    scale = min(width / image_width, height / image_height)
    w, h = int(round(image_width * scale)), int(round(image_height * scale))
    resized = cv2.resize(image, (w, h), interpolation=cv2.INTER_LINEAR)
    left, top = (width - w) // 2, (height - h) // 2
    padded = cv2.copyMakeBorder(resized, top, height - h - top, left, width - w - left,
                                cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return cv2.cvtColor(padded, cv2.COLOR_BGR2RGB), (w / image_width, h / image_height, left, top)


def decode(cv2, np, frame, predictions, names, confidence, transform):
    scale_x, scale_y, left, top = transform
    detections = []
    # Select the highest-scoring COCO class for each anchor before filtering target classes.
    scores = predictions[4:, :]
    winners = scores.argmax(axis=0)
    for class_id, name in names.items():
        columns = np.flatnonzero((winners == class_id) & (scores[class_id] >= confidence))
        columns = sorted(columns, key=lambda i: -scores[class_id, i])[:300]
        boxes, confidences = [], []
        for index in columns:
            cx, cy, width, height = predictions[:4, index]
            score = float(scores[class_id, index])
            if not all(math.isfinite(v) for v in (cx, cy, width, height, score)) or min(width, height) <= 0:
                continue
            boxes.append([float(cx - width / 2), float(cy - height / 2), float(width), float(height)])
            confidences.append(score)
        if not boxes:
            continue
        for index in np.asarray(cv2.dnn.NMSBoxes(boxes, confidences, confidence - 1e-7, 0.45)).reshape(-1):
            x, y, w, h = boxes[index]
            box = ((x - left) / scale_x, (y - top) / scale_y,
                   (x + w - left) / scale_x, (y + h - top) / scale_y)
            detection = make_detection(frame, name, confidences[index], box, confidence)
            if detection is not None:
                detections.append(detection)
    return detections


class TensorRTDetector(Detector):
    def __init__(self, config):
        model = Path(config["model"])
        metadata = Path(config["metadata"])
        if not model.is_file() or not metadata.is_file():
            raise ValueError("TensorRT requires a local --model engine and --metadata JSON")
        spec = json.loads(metadata.read_text(encoding="utf-8"))
        if spec.get("format") != "yolo11-raw-v1" or spec.get("input_size") != config["input_size"]:
            raise ValueError("TensorRT metadata and --input-size must describe this fixed-size engine")
        self.names = class_ids(spec["names"])
        try:
            import cv2
            import numpy as np
            import pycuda.driver as cuda
            import tensorrt as trt
        except ImportError as error:
            raise RuntimeError("TensorRT backend requires the Jetson TensorRT 8 Python bindings and PyCUDA") from error

        self.cv2, self.np, self.cuda = cv2, np, cuda
        self.confidence, self.timing = config["confidence"], {}
        cuda.init()
        device = config["device"]
        if device != "cuda" and not (device.startswith("cuda:") and device[5:].isdigit()):
            raise ValueError("Use --device cuda:0 for the Jetson GPU")
        self.cuda_context = cuda.Device(int(device[5:]) if ":" in device else 0).make_context()
        self.allocations = []
        try:
            self.logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.logger)
            self.engine = self.runtime.deserialize_cuda_engine(model.read_bytes())
            if self.engine is None or self.engine.num_bindings != 2 or self.engine.has_implicit_batch_dimension:
                raise ValueError("Expected a TensorRT 8 explicit-batch engine with two bindings")
            self.context = self.engine.create_execution_context()
            if self.context is None:
                raise RuntimeError("Could not allocate a TensorRT execution context")
            self.input_index = next(i for i in range(2) if self.engine.binding_is_input(i))
            self.output_index = 1 - self.input_index
            self.shapes = [tuple(self.engine.get_binding_shape(i)) for i in range(2)]
            self.types = [trt.nptype(self.engine.get_binding_dtype(i)) for i in range(2)]
            size = config["input_size"]
            out = self.shapes[self.output_index]
            if (self.shapes[self.input_index] != (1, 3, size, size) or len(out) != 3
                    or out[:2] != (1, len(spec["names"]) + 4) or out[-1] <= 0
                    or any(t not in (np.float16, np.float32) for t in self.types)):
                raise ValueError("Unexpected TensorRT shape/dtype. Use the documented raw YOLO11 export.")
            self.stream = cuda.Stream()
            self.host_out = cuda.pagelocked_empty(out, dtype=self.types[self.output_index])
            self.host_in = cuda.pagelocked_empty(self.shapes[self.input_index], dtype=self.types[self.input_index])
            for buf in (self.host_in, self.host_out) if self.input_index == 0 else (self.host_out, self.host_in):
                self.allocations.append(cuda.mem_alloc(buf.nbytes))
        except Exception:
            self._release()
            self.cuda_context.pop()
            self.cuda_context.detach()
            raise
        self.cuda_context.pop()

    def detect(self, frame):
        start = perf_counter()
        _, _, h, w = self.shapes[self.input_index]
        rgb, transform = letterbox(self.cv2, frame.image, h, w)
        self.host_in[0] = rgb.transpose(2, 0, 1).astype(self.np.float32) / 255.0
        prepared = perf_counter()
        self.cuda_context.push()
        try:
            self.cuda.memcpy_htod_async(self.allocations[self.input_index], self.host_in, self.stream)
            if not self.context.execute_async_v2([int(ptr) for ptr in self.allocations], self.stream.handle):
                raise RuntimeError("TensorRT inference failed")
            self.cuda.memcpy_dtoh_async(self.host_out, self.allocations[self.output_index], self.stream)
            self.stream.synchronize()
        finally:
            self.cuda_context.pop()
        done = perf_counter()
        result = decode(self.cv2, self.np, frame, self.host_out[0], self.names, self.confidence, transform)
        self.timing = {"preprocess_ms": (prepared - start) * 1000, "inference_ms": (done - prepared) * 1000,
                       "postprocess_ms": (perf_counter() - done) * 1000}
        return result

    def _release(self):
        for allocation in self.allocations:
            allocation.free()
        self.allocations.clear()
        self.context = self.engine = self.runtime = self.stream = None

    def close(self):
        self.cuda_context.push()
        try:
            self._release()
        finally:
            self.cuda_context.pop()
            self.cuda_context.detach()
