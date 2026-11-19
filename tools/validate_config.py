"""Validate a settings overlay and ROI before launching the engine."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from siteguard.config import EXAMPLE_ROI, load
from siteguard.engine.roi_manager import validate_zones


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--roi")
    args = parser.parse_args()
    config = load(args.config)
    path = Path(args.roi or config["roi_file"])
    if args.roi is None and not path.is_file():
        path = EXAMPLE_ROI
    zones = validate_zones(json.loads(path.read_text(encoding="utf-8")))["zones"]
    print("{} polygons validated in {}".format(len(zones), path))


if __name__ == "__main__":
    main()
