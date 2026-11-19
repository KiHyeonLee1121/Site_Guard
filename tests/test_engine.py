import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from siteguard.config import EXAMPLE_ROI, load
from siteguard.engine.controller import ActionController
from siteguard.engine.dwell_timer import DwellTimer
from siteguard.engine.multi_object import aggregate
from siteguard.engine.roi_manager import ROIManager, contains, validate_zones
from siteguard.engine.state_machine import TrackState
from siteguard.hardware.mock_hardware import MockActuator
from siteguard.hardware.pir_manager import PIR
from siteguard.pipeline import Pipeline
from siteguard.schemas import OFF, Detection, TrackStatus
from siteguard.vision.detector_mock import MockDetector
from siteguard.vision.frame_manager import FrameGate
from siteguard.vision.sources import MockSource
from siteguard.vision.tracker import Tracker


class GeometryTests(unittest.TestCase):
    def test_polygon_boundary_concave_and_exterior(self):
        points = [(0, 0), (1, 0), (1, 1), (0.5, 0.5), (0, 1)]
        self.assertTrue(contains(points, (0.1, 0.6)))
        self.assertTrue(contains(points, (0.75, 0.75)))
        self.assertFalse(contains(points, (0.5, 0.9)))

    def test_uses_foot_point_and_most_protective_zone(self):
        payload = json.loads(EXAMPLE_ROI.read_text(encoding="utf-8"))
        self.assertEqual(ROIManager.classify(payload, (65, 5, 85, 80), 100, 100), 3)
        self.assertEqual(ROIManager.classify(payload, (130, 10, 170, 160), 200, 200), 3)
        self.assertEqual(ROIManager.classify(payload, (43, 5, 57, 80), 100, 100), 2)

    def test_rejects_polygon_crossing_duplicates_and_bounds(self):
        examples = [
            [[0, 0], [0.9, 0.9], [0, 0.6], [1, 0]],
            [[0, 0], [1, 0], [0, 0]],
            [[0, 0], [1.1, 0], [0, 1]],
        ]
        for points in examples:
            with self.subTest(points=points), self.assertRaises(ValueError):
                validate_zones({"zones": [{"level": 2, "name": "A", "points": points}]})

    def test_atomic_save_and_rejects_conflicting_edits(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "roi.json")
            manager = ROIManager(path, EXAMPLE_ROI)
            self.assertEqual(manager.save({"zones": []}, 0), 1)
            with self.assertRaises(ValueError):
                manager.save({"zones": []}, 0)
            self.assertEqual(ROIManager(path, EXAMPLE_ROI).snapshot()[1], {"zones": []})
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["roi.json"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.policy = load()["policy"]

    def test_dwell_ignores_long_and_unobserved_intervals(self):
        timer = DwellTimer(0.6)
        for t in (0, 0.2, 0.4, 4.0):
            timer.update(t, True)
        timer.missed()
        self.assertAlmostEqual(timer.update(4.4, True), 0.4)
        self.assertEqual(timer.update(4.5, False), 0)

    def test_critical_requires_consecutive_seen_frames(self):
        state = TrackState(1, "person", self.policy)
        self.assertFalse(state.update(0.0, 3))
        self.assertFalse(state.update(0.1, None))
        self.assertFalse(state.update(0.2, 3))
        self.assertEqual(state.update(0.3, 3)[0].kind, "critical")

    def test_boundary_hysteresis_and_confirmed_clear(self):
        state = TrackState(1, "person", self.policy)
        state.update(0, 3)
        state.update(0.1, 3)
        for t, roi in ((0.2, 1), (0.3, 3), (0.4, 2), (0.5, 1)):
            state.update(t, roi)
        self.assertEqual(state.status().roi, 3)
        self.assertEqual(state.status().state, "CRITICAL")
        state.update(0.7, 1)
        self.assertEqual(state.status().state, "CLEARING")
        self.assertEqual(state.update(1.7, 1)[0].kind, "cleared")
        self.assertEqual(state.status().state, "OBSERVING")

    def test_reannouncement_capped_and_review_emitted_once(self):
        state = TrackState(1, "dog", self.policy)
        state.update(0, 3)
        state.update(0.1, 3)
        self.assertEqual(state.update(12.2, 3)[0].kind, "reannouncement")
        self.assertEqual(state.update(24.3, 3)[0].kind, "review_required")
        self.assertFalse(state.update(36.4, 3))
        self.assertEqual(state.lost()[0].kind, "lost")

    def test_aggregate_severity_then_configured_class(self):
        person = TrackStatus(1, "person", 2, 5, "WARNING", 1, 1)
        dog = TrackStatus(2, "dog", 3, 0, "CRITICAL", 2, 1)
        self.assertEqual(aggregate([person, dog], self.policy).sound, "tone_critical")
        person = person._replace(level=2)
        self.assertEqual(aggregate([person, dog], self.policy).sound, "voice_critical")
        self.assertEqual(aggregate([person, dog], dict(self.policy, person_first=False)).sound, "tone_critical")
        self.assertEqual(aggregate([], self.policy), OFF)

    def test_switching_does_not_replay_previous_audio(self):
        actuator = MockActuator()
        controller = ActionController(actuator)
        a = OFF._replace(level=1, brightness=50, sound="voice_warning", sound_revision=(1, 1))
        b = a._replace(sound="tone_warning", sound_revision=(2, 1))
        controller.apply(a)
        controller.apply(b)
        controller.apply(a)
        self.assertEqual([item["sound"] for item in actuator.drain()], ["voice_warning", "tone_warning", "off"])

    def test_pir_boost_does_not_disable_idle_analysis(self):
        pir = PIR(load()["pir"])
        gate = FrameGate(2, 10)
        self.assertTrue(gate.allow(0, pir.boosted(0)))
        self.assertFalse(gate.allow(0.2, pir.boosted(0.2)))
        pir.update(True, 0.22)
        self.assertTrue(gate.allow(0.24, pir.boosted(0.24)))
        pir.update(False, 1)
        self.assertTrue(pir.boosted(2))
        self.assertFalse(pir.boosted(6))
        self.assertTrue(gate.allow(6, False))

    def test_unknown_or_inconsistent_configuration(self):
        with self.assertRaises(ValueError):
            load(overrides={"source": {"kind": "camera"}})
        with self.assertRaises(ValueError):
            load(overrides={"vision": {"idle_hz": -1}})
        with self.assertRaises(ValueError):
            load(overrides={"policy": {"person_frist": False}})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = load()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.actuator = MockActuator()
        self.engine = Pipeline(MockDetector(0.45), Tracker(self.config["tracker"]),
                               ROIManager(Path(self.temp.name, "roi.json"), EXAMPLE_ROI),
                               self.config["policy"], ActionController(self.actuator))

    def simulate(self, scenario):
        events, outputs = [], []
        source = MockSource(self.config["source"], scenario, False)
        for frame in source.frames(Event()):
            _, _, transitions, output, _, _ = self.engine.step(frame)
            events.extend((frame.timestamp, event) for event in transitions)
            outputs.append((frame.timestamp, output))
        return events, outputs

    def test_roi1_passage_stays_quiet(self):
        events, outputs = self.simulate("roi1")
        self.assertFalse(events)
        self.assertTrue(all(output == OFF for _, output in outputs))

    def test_person_dwell_and_exit(self):
        events, outputs = self.simulate("roi2")
        self.assertEqual([event.kind for _, event in events], ["warning", "cleared"])
        self.assertGreaterEqual(events[0][0], 5.5)
        self.assertTrue(any(output.sound == "voice_warning" for _, output in outputs))
        self.assertEqual(outputs[-1][1], OFF)

    def test_direct_roi3_and_dog_dwell(self):
        events, outputs = self.simulate("critical")
        self.assertEqual(events[0][1].kind, "critical")
        self.assertAlmostEqual(events[0][0], 0.55)
        self.assertTrue(any(output.sound == "voice_critical" for _, output in outputs))
        events, outputs = self.simulate("dog")
        self.assertEqual(events[0][1].kind, "warning")
        self.assertAlmostEqual(events[0][0], 3.5)
        self.assertTrue(any(output.sound == "tone_warning" for _, output in outputs))

    def test_multiple_objects_priority(self):
        events, outputs = self.simulate("multi")
        self.assertEqual([event.kind for _, event in events[:2]], ["warning", "critical"])
        self.assertTrue(any(output.sound == "tone_critical" for _, output in outputs))
        self.assertEqual(outputs[-1][1], OFF)

    def test_missing_detection_retains_then_clears(self):
        events, outputs = self.simulate("dropout")
        held = [output.level for t, output in outputs if 6.2 <= t < 6.5]
        self.assertTrue(held and all(held))
        self.assertEqual([event.kind for _, event in events], ["warning", "lost"])
        self.assertEqual(events[0][1].status.track_id, events[1][1].status.track_id)
        self.assertEqual(outputs[-1][1], OFF)

    def test_expiry_and_new_id(self):
        tracker = Tracker(self.config["tracker"])
        det = Detection("dog", 0.9, (10, 10, 30, 35), 0)
        observed, expired = tracker.update([det], 0, 100, 100)
        number = observed[0].track_id
        observed, expired = tracker.update([], 0.3, 100, 100)
        self.assertEqual(observed[0].track_id, number)
        self.assertFalse(observed[0].visible)
        observed, expired = tracker.update([det._replace(timestamp=2.1)], 2.1, 100, 100)
        self.assertEqual(expired, [number])
        self.assertNotEqual(observed[0].track_id, number)
