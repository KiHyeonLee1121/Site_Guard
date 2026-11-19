import base64
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from siteguard.config import EXAMPLE_ROI, load
from siteguard.dashboard.server import Dashboard, DashboardState
from siteguard.engine.roi_manager import ROIManager
from siteguard.hardware.arduino_serial import SerialLink, SerialProtocolError
from siteguard.hardware.serial_protocol import encode, parse_reply
from siteguard.network.cloud_client import HttpCloud, validate_url
from siteguard.network.event_sync import EventSync
from siteguard.storage.database import Database


class FakeSerial:
    def __init__(self, replies):
        self.replies, self.writes, self.timeout = list(replies), [], 0

    def write(self, packet):
        self.writes.append(packet)
        return len(packet)

    def read_until(self, expected, size):
        if self.replies:
            return self.replies.pop(0)
        time.sleep(self.timeout)
        return b""


class SerialTests(unittest.TestCase):
    def test_output_wire_format_and_ack(self):
        self.assertEqual(encode("A0B1C2D3", "SET_OUTPUT", 80, "tone_critical"),
                         b"SG1 A0B1C2D3 SET_OUTPUT 80 tone_critical\n")
        reply = parse_reply(b"SG1 A0B1C2D3 ACK 80 tone_critical 1\r\n")
        self.assertTrue(reply.ok)
        self.assertTrue(reply.pir)
        self.assertEqual(reply.brightness, 80)

    def test_bad_arguments_rejected_and_nack_decoded(self):
        with self.assertRaises(ValueError):
            encode("A0B1C2D3", "SET_LED", True)
        with self.assertRaises(ValueError):
            parse_reply(b"SG1 A0B1C2D3 ACK 0 off -")
        self.assertEqual(parse_reply(b"SG1 A0B1C2D3 NACK BAD_ARGS\n").error, "BAD_ARGS")

    def test_ignores_unmatched_reply_and_retries_same_bytes(self):
        class RetryPort(FakeSerial):
            def read_until(self, expected, size):
                if len(self.writes) == 1 and not self.replies:
                    time.sleep(self.timeout)
                    return b""
                if len(self.writes) == 2:
                    return b"SG1 A0B1C2D3 ACK 40 off -\n"
                return super().read_until(expected, size)

        port = RetryPort([b"SG1 FFFFFFFF ACK 0 off -\n"])
        answer = SerialLink(port, 0.015, 1).send("A0B1C2D3", "SET_LED", 40)
        self.assertEqual(answer.brightness, 40)
        self.assertEqual(port.writes[0], port.writes[1])

    def test_timeout_is_bounded(self):
        port = FakeSerial([])
        with self.assertRaises(SerialProtocolError):
            SerialLink(port, 0.01, 2).send("A0B1C2D3", "PING")
        self.assertEqual(len(port.writes), 3)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(str(Path(self.temp.name, "events.sqlite3")))
        self.addCleanup(self.db.close)

    def test_local_write_and_response_clip_fields(self):
        self.db.add({"id": "id-a", "kind": "critical"}, command_id="A0B1C2D3", clip_pending=True, now=5)
        self.db.save_response({"id": "A0B1C2D3", "ok": True})
        self.db.save_clip(["id-a"], "some.avi")
        event = self.db.get("id-a")
        self.assertEqual(event["local_status"], "stored")
        self.assertTrue(event["arduino_response"]["ok"])
        self.assertEqual(event["clip"], "some.avi")
        self.assertFalse(event["clip_pending"])

    def test_offline_retry_and_success(self):
        class Client:
            online = False
            seen = []

            def send(self, event):
                if not self.online:
                    raise OSError("Offline")
                self.seen.append(event["id"])

        client = Client()
        sync = EventSync(self.db, client, load()["cloud"])
        self.db.add({"id": "id-a", "kind": "critical"}, cloud=True, now=5)
        self.assertEqual(sync.once(5), 0)
        self.assertEqual(self.db.get("id-a")["attempts"], 1)
        client.online = True
        self.assertEqual(sync.once(6), 0)
        self.assertEqual(sync.once(7), 1)
        self.assertEqual(self.db.get("id-a")["cloud_status"], "sent")
        self.assertEqual(sync.once(99), 0)
        self.assertEqual(client.seen, ["id-a"])

    def test_pending_queue_survives_restart(self):
        path = str(Path(self.temp.name, "second.sqlite3"))
        before = Database(path)
        before.add({"id": "id-a", "kind": "output"}, cloud=True, command_id="11111111", now=1)
        before.close()
        after = Database(path)
        try:
            self.assertEqual(after.queue_state(), 1)
            self.assertEqual(after.due(10)[0]["arduino_response"]["error"], "process_restarted")
        finally:
            after.close()

    def test_retention_removes_oldest_and_cleans_stale_references(self):
        self.db.add({"id": "first", "kind": "warning"}, now=1)
        self.db.add({"id": "second", "kind": "warning"}, now=2)
        self.db.save_clip(["first", "second"], "one.avi")
        self.db.forget_clips(["one.avi"])
        self.db.prune(0, 1)
        self.assertIsNone(self.db.get("first"))
        self.assertIsNone(self.db.get("second")["clip"])

    def test_cloud_url_requires_safe_transport_and_has_no_inline_credentials(self):
        for url in ("http://remote.example/", "https://user:pass@host.test/", "file:///tmp/events"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.roi = ROIManager(Path(self.temp.name, "roi.json"), EXAMPLE_ROI)
        self.config = dict(load()["dashboard"], port=0)

    def start(self, token="", host=None):
        if host:
            self.config["host"] = host
        state = DashboardState({"source": "mock"})
        dashboard = Dashboard(self.config, token, state, self.roi, self.db, load()["policy"])
        self.addCleanup(dashboard.close)
        return "http://127.0.0.1:{}".format(dashboard.http.server_port)

    def test_static_status_and_no_mock_pixels(self):
        address = self.start()
        with urlopen(address + "/", timeout=2) as response:
            self.assertIn(b"SiteGuard", response.read())
        with urlopen(address + "/api/status", timeout=2) as response:
            self.assertEqual(json.load(response)["source"], "mock")
        with self.assertRaises(HTTPError) as caught:
            urlopen(address + "/api/frame.jpg", timeout=2)
        self.assertEqual(caught.exception.code, 404)

    def test_origin_rejected_then_save_and_read(self):
        address = self.start()
        headers = {"Content-Type": "application/json", "X-SiteGuard-ROI": "1"}
        payload = b'{"zones":[],"revision":0}'
        wrong = Request(address + "/api/roi", payload, dict(headers, Origin="http://foreign.test"), method="PUT")
        with self.assertRaises(HTTPError) as caught:
            urlopen(wrong, timeout=2)
        self.assertEqual(caught.exception.code, 403)
        good = Request(address + "/api/roi", payload, dict(headers, Origin=address), method="PUT")
        with urlopen(good, timeout=2) as response:
            self.assertEqual(json.load(response)["revision"], 1)
        self.assertTrue(self.roi.path.is_file())

    def test_local_host_rebinding_rejected(self):
        address = self.start()
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(address, headers={"Host": "foreign.test"}), timeout=2)
        self.assertEqual(caught.exception.code, 403)

    def test_lan_auth_required_and_succeeds(self):
        with self.assertRaises(ValueError):
            self.start(host="0.0.0.0")
        token = "local-test-token-only-1234567890"
        address = self.start(token, "0.0.0.0")
        with self.assertRaises(HTTPError) as caught:
            urlopen(address + "/api/status", timeout=2)
        self.assertEqual(caught.exception.code, 401)
        auth = base64.b64encode(("siteguard:" + token).encode()).decode()
        with urlopen(Request(address + "/api/status", headers={"Authorization": "Basic " + auth}), timeout=2) as r:
            self.assertEqual(json.load(r)["source"], "mock")


class EndToEndTests(unittest.TestCase):
    def test_full_mock_pipeline_persists_ack_and_queue(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory, "db.sqlite3"))
            result = subprocess.run([sys.executable, "-m", "siteguard", "--source", "mock", "--dry-run",
                                     "--benchmark", "--database", path, "--sync"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["frames"], 720)
            self.assertEqual(summary["events"]["critical"], 1)
            self.assertEqual(summary["events"]["warning"], 2)
            self.assertGreaterEqual(summary["events"]["cleared"], 2)
            db = Database(path)
            try:
                warning = next(item for item in db.recent() if item["kind"] == "warning")
                self.assertTrue(warning["arduino_response"]["ok"])
                self.assertEqual(warning["cloud_status"], "pending")
            finally:
                db.close()
