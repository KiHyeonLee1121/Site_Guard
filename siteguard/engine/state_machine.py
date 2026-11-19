"""Independent track state and bounded announcement policy."""

from siteguard.schemas import PolicyEvent, TrackStatus
from .dwell_timer import DwellTimer


class TrackState:
    def __init__(self, track_id, class_name, config):
        self.track_id = track_id
        self.class_name = class_name
        self.config = config
        self.timer = DwellTimer(config["max_dwell_gap"])
        self.roi = self.level = self.critical_hits = self.repeats = self.sound_revision = 0
        self.lower_since = self.clear_since = self.last_sound = None
        self.last_critical = None
        self.review_sent = False
        self.state = "IDLE"

    def status(self):
        return TrackStatus(self.track_id, self.class_name, self.roi, self.timer.seconds,
                           self.state, self.level, self.sound_revision)

    def _enter_warning(self, level, now):
        self.level = level
        self.clear_since = None
        self.last_sound = now
        self.repeats = 0
        self.review_sent = False
        self.sound_revision += 1
        self.state = "CRITICAL" if level == 2 else "WARNING"
        return PolicyEvent("critical" if level == 2 else "warning", self.status())

    def _clear(self, reason):
        had_warning = self.level > 0
        self.level = self.roi = 0
        self.lower_since = self.clear_since = None
        self.timer.update(0, False)
        self.state = "IDLE"
        return [PolicyEvent(reason, self.status())] if had_warning else []

    def lost(self):
        return self._clear("lost")

    def update(self, now, raw_roi):
        if raw_roi is None:
            self.critical_hits = 0
            self.last_critical = None
            self.lower_since = self.clear_since = None
            self.timer.missed()
            return []

        if raw_roi == 3:
            if self.last_critical is None or now - self.last_critical > self.config["max_dwell_gap"]:
                self.critical_hits = 0
            self.critical_hits += 1
            self.last_critical = now
        else:
            self.critical_hits = 0
            self.last_critical = None
        if raw_roi < self.roi:
            if self.lower_since is None:
                self.lower_since = now
            if now - self.lower_since + 1e-9 >= self.config["roi_down_sec"]:
                self.roi = raw_roi
        else:
            self.lower_since = None
            self.roi = raw_roi

        if raw_roi == 2 and self.roi != 2:
            # A tentative downward transition provides no dwell evidence.
            self.timer.missed()
        else:
            self.timer.update(now, raw_roi == 2 and self.roi == 2)
        if self.critical_hits >= self.config["critical_frames"] and self.level < 2:
            return [self._enter_warning(2, now)]
        threshold = self.config["dwell"][self.class_name]
        if self.level == 0 and raw_roi == self.roi == 2 and self.timer.seconds + 1e-9 >= threshold:
            return [self._enter_warning(1, now)]

        if not self.level:
            self.state = {0: "IDLE", 1: "OBSERVING", 2: "DWELLING", 3: "OBSERVING"}[self.roi]
            return []
        if self.roi < 2:
            if self.clear_since is None:
                self.clear_since = now
            self.state = "CLEARING"
            if now - self.clear_since + 1e-9 >= self.config["clear_sec"]:
                had_roi = self.roi
                self._clear("cleared")
                self.roi = had_roi
                self.state = "OBSERVING" if had_roi else "IDLE"
                return [PolicyEvent("cleared", self.status())]
            return []

        self.clear_since = None
        self.state = "CRITICAL" if self.level == 2 else "WARNING"
        if raw_roi >= 2 and now - self.last_sound >= self.config["repeat_sec"]:
            if self.repeats < self.config["max_repeats"]:
                self.repeats += 1
                self.sound_revision += 1
                self.last_sound = now
                return [PolicyEvent("reannouncement", self.status())]
            if not self.review_sent:
                self.review_sent = True
                return [PolicyEvent("review_required", self.status())]
        return []
