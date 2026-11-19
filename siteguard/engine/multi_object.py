"""Resolve independent warning states into shared LED and speaker output."""

from siteguard.schemas import OFF, Output


def aggregate(statuses, policy):
    active = [status for status in statuses if status.level]
    if not active:
        return OFF
    preferred = "person" if policy["person_first"] else "dog"
    selected = max(active, key=lambda item: (item.level, item.class_name == preferred, -item.track_id))
    severity = "critical" if selected.level == 2 else "warning"
    sound = ("voice_" if selected.class_name == "person" else "tone_") + severity
    return Output(selected.level, policy["brightness"][severity], sound, (selected.track_id, selected.sound_revision))
