"""In-memory application of the serial protocol's output semantics."""

from collections import deque

from .actuator import CommandIDs


class MockActuator:
    def __init__(self):
        self.ids = CommandIDs()
        self.commands = deque(maxlen=256)
        self.responses = []
        self.status = {"connection": "mock", "brightness": 0, "sound": "off", "pir": None}

    def submit(self, output, play=True):
        command_id = self.ids.next()
        sound = output.sound if play else "off"
        self.commands.append((command_id, output))
        self.status.update(brightness=output.brightness, sound=sound)
        self.responses.append({"id": command_id, "ok": True, "brightness": output.brightness,
                               "sound": sound, "pir": self.status["pir"], "serial_ms": 0.0})
        return command_id

    def drain(self):
        results, self.responses = self.responses, []
        return results

    def close(self):
        self.status.update(brightness=0, sound="off")
