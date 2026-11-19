"""Export fixed-size raw YOLO11 output and write matching binding metadata."""

import argparse
import json
from pathlib import Path
import shutil

from prepare_model import digest

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, default=ROOT / "models/local/yolo11n.pt")
    parser.add_argument("--size", type=int, choices=(320, 416, 640), default=320)
    args = parser.parse_args()
    weights = args.weights.resolve()
    if not weights.is_file():
        parser.error("Run scripts/setup_model.sh yolo first")
    from ultralytics import YOLO, __version__
    from onnx import checker, load

    directory = ROOT / "models" / "local"
    directory.mkdir(parents=True, exist_ok=True)
    named_weights = directory / ("yolo11n-" + str(args.size) + ".pt")
    if weights != named_weights:
        shutil.copyfile(str(weights), str(named_weights))
    model = YOLO(str(named_weights), task="detect")
    path = Path(model.export(format="onnx", opset=12, imgsz=args.size, batch=1, dynamic=False,
                             simplify=False, half=False, nms=False, device="cpu"))
    checker.check_model(load(str(path)))
    meta = {"format": "yolo11-raw-v1", "input_size": args.size, "names": model.names,
            "opset": 12, "ultralytics": __version__, "weights_sha256": digest(weights),
            "onnx_sha256": digest(path)}
    metadata = path.with_suffix(".json")
    metadata.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("{}\n{}".format(path, metadata))


if __name__ == "__main__":
    main()
