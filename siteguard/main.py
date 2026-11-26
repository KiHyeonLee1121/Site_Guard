"""SiteGuard command-line frontend."""

import argparse
import json
import logging
import signal
from threading import Event

from siteguard.config import load, load_env, merge, validate
from siteguard.runtime import configure_logging, run
from siteguard.vision.sources import SCENARIOS


def parse(argv=None):
    parser = argparse.ArgumentParser(description="SiteGuard edge monitoring engine")
    parser.add_argument("--config", help="JSON-compatible YAML overlay")
    parser.add_argument("--source", choices=("mock", "camera", "video"))
    parser.add_argument("--detector", "--backend", choices=("mock", "yolo", "jetson", "tensorrt"))
    parser.add_argument("--video", help="Input MP4/AVI path")
    parser.add_argument("--output-video", help="Save annotated video playback as a new MP4")
    parser.add_argument("--camera-index", type=int)
    parser.add_argument("--gstreamer", help="OpenCV capture pipeline ending in appsink")
    parser.add_argument("--model", help="Weights, SSD directory or TensorRT engine path")
    parser.add_argument("--metadata", help="Model metadata JSON for TensorRT")
    parser.add_argument("--device", help="cpu or cuda:0, depending on the selected backend")
    parser.add_argument("--input-size", type=int)
    parser.add_argument("--roi-file")
    parser.add_argument("--database")
    parser.add_argument("--serial-port", help="Enable physical Arduino on this port")
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--dashboard-host")
    parser.add_argument("--dashboard-port", type=int)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Replace physical Arduino output with mock hardware")
    parser.add_argument("--realtime", action="store_true", help="Pace video and mock input on the playback clock")
    parser.add_argument("--stay-open", action="store_true", help="Keep enabled dashboard available after finite playback")
    parser.add_argument("--scenario", choices=SCENARIOS, default="tour")
    parser.add_argument("--max-frames", type=int, help="Stop after this many analyzed frames")
    parser.add_argument("--benchmark", action="store_true", help="Emit a machine-readable latency summary")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def config_for(args):
    selected = load(args.config, validate_inputs=False)
    source = args.source or ("video" if args.video else selected["source"]["kind"])
    backend = args.detector or selected["vision"]["backend"]
    if args.detector is None:
        if source == "mock":
            backend = "mock"
        elif backend == "mock":
            backend = "yolo"
    source_cfg = {"kind": source}
    vision_cfg = {"backend": backend}
    overrides = {"source": source_cfg, "vision": vision_cfg, "serial": {}, "dashboard": {},
                 "storage": {}, "recording": {}, "cloud": {}}
    for target, pairs in (
        (source_cfg, {"camera_index": args.camera_index, "gstreamer": args.gstreamer}),
        (vision_cfg, {"model": args.model, "metadata": args.metadata, "input_size": args.input_size, "device": args.device}),
        (overrides["dashboard"], {"port": args.dashboard_port, "host": args.dashboard_host}),
        (overrides["storage"], {"database": args.database}),
        (overrides, {"roi_file": args.roi_file}),
    ):
        target.update({key: value for key, value in pairs.items() if value is not None})
    if not args.model and (not selected["vision"]["model"] or selected["vision"]["backend"] != backend):
        defaults = {"yolo": "models/local/yolo11n.pt", "jetson": "models/local/jetson"}
        if backend in defaults:
            vision_cfg["model"] = defaults[backend]
    if args.serial_port:
        overrides["serial"].update(enabled=True, port=args.serial_port)
    if args.dry_run or source == "mock":
        overrides["serial"]["enabled"] = False
    if args.dashboard or args.dashboard_host is not None or args.dashboard_port is not None:
        overrides["dashboard"]["enabled"] = True
    if args.record:
        overrides["recording"]["enabled"] = True
    if args.sync:
        overrides["cloud"]["enabled"] = True
    if args.max_frames is not None and args.max_frames < 1:
        raise ValueError("--max-frames must be positive")
    if args.output_video and source != "video":
        raise ValueError("--output-video requires a video input")
    if args.stay_open and not (selected["dashboard"]["enabled"] or overrides["dashboard"].get("enabled")):
        raise ValueError("--stay-open requires an enabled dashboard")
    merge(selected, overrides)
    return validate(selected)


def main(argv=None):
    args = parse(argv)
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, frame: stop.set())
    try:
        load_env()
        config = config_for(args)
        configure_logging(config["log_file"], args.debug)
        summary = run(config, args, stop)
        if args.benchmark:
            print(json.dumps(summary, sort_keys=True), flush=True)
        else:
            logging.getLogger("siteguard").info("Run summary %s", summary)
        return 0 if summary["storage_errors"] == 0 else 3
    except (OSError, ValueError, RuntimeError) as error:
        logging.getLogger("siteguard").error("%s", error, exc_info=args.debug)
        return 2
    except Exception:
        logging.getLogger("siteguard").exception("SiteGuard stopped due to an unexpected error")
        return 2
