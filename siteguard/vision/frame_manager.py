"""Camera-only rate limiting. Skipped frames are not tracker misses."""


class FrameGate:
    def __init__(self, idle_hz, active_hz):
        self.period = {False: 1.0 / idle_hz, True: 1.0 / active_hz}
        self.last = None

    def allow(self, now, active):
        if self.last is not None and now - self.last + 1e-9 < self.period[bool(active)]:
            return False
        self.last = now
        return True
