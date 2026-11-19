"""Validated configuration and optional environment variables."""

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
if not (CONFIG_DIR / "default.yaml").is_file():
    CONFIG_DIR = Path(sys.prefix) / "share" / "siteguard" / "config"
DEFAULT = CONFIG_DIR / "default.yaml"
EXAMPLE_ROI = CONFIG_DIR / "roi.example.json"


def read_mapping(path):
    with Path(path).open(encoding="utf-8") as handle:
        content = handle.read()
    try:
        data = json.loads(content)
    except ValueError:
        try:
            import yaml
        except ImportError:
            raise ValueError("Use JSON-compatible YAML or install PyYAML: {}".format(path))
        data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError("Expected a mapping: {}".format(path))
    return data


def merge(target, updates, prefix=""):
    for key, value in updates.items():
        path = prefix + key
        if key not in target:
            raise ValueError("Unknown setting: " + path)
        expected = target[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise ValueError("Expected mapping: " + path)
            merge(expected, value, path + ".")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if isinstance(value, bool) or not isinstance(value, type(expected) if isinstance(expected, int) else (int, float)):
                raise ValueError("Invalid numeric type: " + path)
            if value < 0 or (isinstance(value, float) and not math.isfinite(value)):
                raise ValueError("Expected finite nonnegative value: " + path)
            target[key] = value
        elif isinstance(value, type(expected)):
            target[key] = value
        else:
            raise ValueError("Invalid type: " + path)


def validate(c):
    s, v, t, p = (c[k] for k in ("source", "vision", "tracker", "policy"))
    if s["kind"] not in ("mock", "video", "camera") or v["backend"] not in ("mock", "jetson", "yolo", "tensorrt"):
        raise ValueError("Unknown source or inference backend")
    if (s["kind"] == "mock") != (v["backend"] == "mock"):
        raise ValueError("Mock source requires the mock detector. Camera/video require a real detector.")
    if not (0 < v["idle_hz"] <= v["active_hz"] and 0 < v["confidence"] <= 1 and v["input_size"] >= 32):
        raise ValueError("Invalid inference rate, threshold or input size")
    if min(s["width"], s["height"], s["fps"], s["reconnect_sec"], s["stale_sec"]) <= 0:
        raise ValueError("Capture dimensions, FPS and recovery times must be positive")
    if not (0 < t["min_iou"] <= 1 and 0 < t["center_gate"] <= 1 and t["max_tracks"] and t["ttl"] > 0):
        raise ValueError("Invalid tracker settings")
    if not (p["critical_frames"] >= 1 and p["max_dwell_gap"] > 0 and p["repeat_sec"] > 0):
        raise ValueError("Invalid policy timing")
    if max(p["brightness"].values()) > 100:
        raise ValueError("Brightness must be within 0–100")
    serial = c["serial"]
    # The firmware drops outputs after a 3-second contact lapse.
    if not (0 < serial["heartbeat_sec"] < 3 and 0 < serial["timeout"] < 3
            and serial["baud"] and serial["reconnect_sec"] and serial["retries"] <= 5):
        raise ValueError("Invalid serial timing, baud, or retry limit")
    if not (c["cloud"]["timeout"] > 0 and 0 < c["cloud"]["retry_base_sec"] <= c["cloud"]["retry_max_sec"]):
        raise ValueError("Invalid cloud retry settings")
    dash = c["dashboard"]
    if not (0 <= dash["port"] <= 65535 and dash["preview_hz"] > 0 and dash["preview_width"] > 0):
        raise ValueError("Invalid dashboard options")
    rec = c["recording"]
    if min(rec["fps"], rec["width"], rec["buffer_bytes"], rec["max_clip_bytes"], rec["retention_days"],
           c["storage"]["retention_days"], c["storage"]["max_events"]) <= 0 or rec["max_total_bytes"] < rec["max_clip_bytes"]:
        raise ValueError("Invalid recording or storage limits")
    return c


def load(path=None, overrides=None, validate_inputs=True):
    config = read_mapping(DEFAULT)
    if path:
        merge(config, read_mapping(path))
    if overrides:
        merge(config, overrides)
    return validate(config) if validate_inputs else config


def load_env(path=".env"):
    path = Path(path)
    if not path.is_file():
        return
    allowed = {"SITEGUARD_DASHBOARD_TOKEN", "SITEGUARD_CLOUD_TOKEN", "SITEGUARD_CLOUD_URL"}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key in allowed:
            os.environ.setdefault(key, value.strip().strip("'\""))
