"""Contracts shared by vision, policy, runtime and hardware."""

from typing import Any, Optional, Tuple, NamedTuple


class Frame(NamedTuple):
    image: Any
    width: int
    height: int
    timestamp: float
    captured_at: Optional[float]
    fixture: Any


class Detection(NamedTuple):
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    timestamp: float


class Observation(NamedTuple):
    track_id: int
    detection: Detection
    visible: bool


class TrackStatus(NamedTuple):
    track_id: int
    class_name: str
    roi: int
    dwell: float
    state: str
    level: int
    sound_revision: int


class PolicyEvent(NamedTuple):
    kind: str
    status: TrackStatus


class Output(NamedTuple):
    level: int
    brightness: int
    sound: str
    sound_revision: Tuple[int, int]


OFF = Output(0, 0, "off", (0, 0))
