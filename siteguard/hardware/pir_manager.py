"""Auxiliary motion hold and debounced change events."""


class PIR:
    def __init__(self, config):
        self.config = config
        self.active = None
        self.last_motion = None

    def update(self, value, now):
        if value is True:
            self.last_motion = now
        if value is None or value == self.active:
            return None
        previous, self.active = self.active, value
        if previous is None and not self.config["emit_initial"]:
            return None
        return "pir_motion" if value else "pir_clear"

    def boosted(self, now):
        return self.last_motion is not None and now - self.last_motion <= self.config["hold_sec"]
