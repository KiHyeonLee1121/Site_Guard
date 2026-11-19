"""Dwell accumulates only between sufficiently close observations in ROI 2."""

class DwellTimer:
    def __init__(self, max_gap):
        self.max_gap = max_gap
        self.seconds = 0.0
        self.last = None

    def update(self, now, in_zone):
        if not in_zone:
            self.seconds = 0.0
            self.last = None
        else:
            if self.last is not None and 0 <= now - self.last <= self.max_gap:
                self.seconds += now - self.last
            self.last = now
        return self.seconds

    def missed(self):
        self.last = None
