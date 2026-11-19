"""Isolated USB serial worker with ACK retry, heartbeat and reconnect."""

from collections import deque
import logging
from threading import Condition, Event, Thread
from time import monotonic

from .actuator import CommandIDs
from .serial_protocol import MAX_LINE, encode, parse_reply
from siteguard.schemas import OFF

LOG = logging.getLogger("siteguard.serial")


class SerialProtocolError(IOError):
    pass


class SerialLink:
    def __init__(self, transport, timeout, retries):
        self.transport, self.timeout, self.retries = transport, timeout, retries

    def send(self, command_id, command, *args):
        packet = encode(command_id, command, *args)
        for _ in range(self.retries + 1):
            if self.transport.write(packet) != len(packet):
                raise SerialProtocolError("Short serial write")
            deadline = monotonic() + self.timeout
            while monotonic() < deadline:
                self.transport.timeout = max(0.001, deadline - monotonic())
                line = self.transport.read_until(b"\n", MAX_LINE)
                try:
                    reply = parse_reply(line)
                except ValueError:
                    if line:
                        LOG.debug("Discarded malformed serial reply")
                    continue
                if reply.command_id == command_id:
                    return reply
        raise SerialProtocolError("ACK timeout for {}".format(command))


class SerialActuator:
    def __init__(self, config, lease_sec=4.0):
        try:
            import serial
        except ImportError as error:
            raise RuntimeError("Serial output requires pyserial") from error
        self.serial = serial
        self.config = config
        self.ids = CommandIDs()
        self.ready = Condition()
        self.stop = Event()
        self.results = deque(maxlen=128)
        self.status = {"connection": "connecting", "brightness": None, "sound": None, "pir": None}
        self.desired, self.pending = OFF, None
        self.lease_sec = lease_sec
        self.last_progress = monotonic()
        self.thread = Thread(target=self._run, name="arduino-serial", daemon=True)
        self.thread.start()

    def _next_id(self):
        with self.ready:
            return self.ids.next()

    def submit(self, output, play=True):
        with self.ready:
            command_id = self.ids.next()
            if self.pending is not None:
                self.results.append({"id": self.pending[0], "ok": False, "error": "superseded", "serial_ms": None})
            self.desired = output
            self.last_progress = monotonic()
            self.pending = (command_id, output, play)
            self.ready.notify()
            return command_id

    def touch(self):
        with self.ready:
            self.last_progress = monotonic()

    def drain(self):
        with self.ready:
            results = list(self.results)
            self.results.clear()
            return results

    def _update_status(self, reply):
        self.status = {"connection": "online", "brightness": reply.brightness,
                       "sound": reply.sound, "pir": reply.pir}

    def _sync(self, link, command, *args):
        reply = link.send(self._next_id(), command, *args)
        if not reply.ok:
            raise SerialProtocolError("{} rejected: {}".format(command, reply.error))
        self._update_status(reply)

    def _serve(self, link):
        self._sync(link, "ALL_OFF")
        restore = True
        leased_off = True
        while not self.stop.is_set():
            with self.ready:
                if not restore:
                    self.ready.wait_for(lambda: self.pending is not None or self.stop.is_set(),
                                        self.config["heartbeat_sec"])
                if self.stop.is_set():
                    return
                pending, self.pending = self.pending, None
                desired = self.desired
                fresh = (monotonic() - self.last_progress < self.lease_sec) or desired == OFF
            if not fresh:
                if pending is not None:
                    self._result(pending[0], {"ok": False, "error": "analysis_stale"}, None)
                if not leased_off:
                    self._sync(link, "ALL_OFF")
                    LOG.warning("Analysis heartbeat expired; Arduino outputs reset")
                restore = False
                leased_off = True
                self._sync(link, "GET_STATUS")
                continue
            if pending is not None:
                self._send_output(link, pending)
            elif desired.brightness and self.status["brightness"] != desired.brightness:
                # Restore LED after reconnect or a stale lease without replaying sound.
                self._sync(link, "SET_LED", desired.brightness)
            else:
                self._sync(link, "GET_STATUS")
            restore = False
            leased_off = desired == OFF

    def _result(self, command_id, result, elapsed):
        result.update(id=command_id, serial_ms=elapsed)
        with self.ready:
            self.results.append(result)

    def _send_output(self, link, pending):
        command_id, output, play = pending
        started = monotonic()
        try:
            reply = link.send(command_id, "SET_OUTPUT", output.brightness, output.sound if play else "off")
        except (OSError, self.serial.SerialException) as error:
            self._result(command_id, {"ok": False, "error": str(error)}, (monotonic() - started) * 1000)
            raise
        self._result(command_id, {"ok": reply.ok, "brightness": reply.brightness, "sound": reply.sound,
                                  "pir": reply.pir, "error": reply.error}, (monotonic() - started) * 1000)
        if not reply.ok:
            raise SerialProtocolError("Arduino rejected SET_OUTPUT: " + reply.error)
        self._update_status(reply)

    def _run(self):
        while not self.stop.is_set():
            link = None
            try:
                with self.serial.Serial(self.config["port"], self.config["baud"], timeout=self.config["timeout"],
                                        write_timeout=self.config["timeout"]) as transport:
                    transport.reset_input_buffer()
                    link = SerialLink(transport, self.config["timeout"], self.config["retries"])
                    try:
                        self._serve(link)
                    finally:
                        if self.stop.is_set():
                            try:
                                with self.ready:
                                    pending, self.pending = self.pending, None
                                if pending is not None and pending[1] == OFF:
                                    self._send_output(link, pending)
                                else:
                                    self._sync(link, "ALL_OFF")
                            except (OSError, self.serial.SerialException) as error:
                                LOG.warning("Shutdown ALL_OFF unconfirmed: %s", error)
            except (OSError, self.serial.SerialException) as error:
                LOG.warning("Serial unavailable on %s: %s", self.config["port"], error)
            self.status = {"connection": "offline", "brightness": None, "sound": None, "pir": None}
            self.stop.wait(self.config["reconnect_sec"])

    def close(self):
        if self.stop.is_set():
            return
        self.stop.set()
        with self.ready:
            if self.pending is not None and self.pending[1] != OFF:
                self.results.append({"id": self.pending[0], "ok": False, "error": "shutdown", "serial_ms": None})
                self.pending = None
            self.ready.notify_all()
        wait = 2 * (self.config["retries"] + 1) * self.config["timeout"] + 0.25
        self.thread.join(wait)
        with self.ready:
            if self.pending is not None:
                self.results.append({"id": self.pending[0], "ok": False, "error": "shutdown_unconfirmed",
                                     "serial_ms": None})
                self.pending = None
