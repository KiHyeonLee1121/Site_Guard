"""Process one analyzed frame through tracking, policy and actuation."""

from time import perf_counter

from siteguard.engine.multi_object import aggregate
from siteguard.engine.roi_manager import ROIManager
from siteguard.engine.state_machine import TrackState


class Pipeline:
    def __init__(self, detector, tracker, roi, policy, controller):
        self.detector = detector
        self.tracker = tracker
        self.roi = roi
        self.policy = policy
        self.controller = controller
        self.states = {}
        self.roi_revision = None
        self.roi_zones = []

    def reset(self):
        events = [event for state in self.states.values() for event in state.lost()]
        self.states.clear()
        self.tracker.tracks.clear()
        return events, self.controller.reset()

    def step(self, frame):
        start = perf_counter()
        detections = self.detector.detect(frame)
        inferred = perf_counter()
        observations, expired = self.tracker.update(
            detections, frame.timestamp, frame.width, frame.height
        )
        tracked = perf_counter()
        revision, zones = self.roi.snapshot()
        self.roi_zones = zones["zones"]
        if self.roi_revision != revision:
            expired = list(self.states)
            self.roi_revision = revision
        events = []
        for key in expired:
            state = self.states.pop(key, None)
            if state is not None:
                events.extend(state.lost())
        for obs in observations:
            det = obs.detection
            if obs.track_id not in self.states:
                if not obs.visible:
                    continue
                self.states[obs.track_id] = TrackState(obs.track_id, det.class_name, self.policy)
            raw = ROIManager.classify(zones, det.bbox, frame.width, frame.height) if obs.visible else None
            events.extend(self.states[obs.track_id].update(frame.timestamp, raw))
        statuses = [state.status() for state in self.states.values()]
        output = aggregate(statuses, self.policy)
        decided = perf_counter()
        command = self.controller.apply(output)
        timing = {"detector_ms": (inferred - start) * 1000, "tracking_ms": (tracked - inferred) * 1000,
                  "policy_ms": (decided - tracked) * 1000}
        timing.update(getattr(self.detector, "timing", {}))
        return observations, statuses, events, output, command, timing
