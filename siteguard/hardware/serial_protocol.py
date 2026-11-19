"""SG1 ASCII framing. A command is retried with the same ID."""

import re
from typing import NamedTuple

VERSION = "SG1"
MAX_LINE = 96
SOUNDS = ("off", "voice_warning", "voice_critical", "tone_warning", "tone_critical")
COMMANDS = {"SET_OUTPUT": 2, "SET_LED": 1, "PLAY_SOUND": 1, "STOP_SOUND": 0,
            "ALL_OFF": 0, "GET_STATUS": 0, "PING": 0}
IDENTIFIER = re.compile(r"[0-9A-F]{8}\Z")
CODE = re.compile(r"[A-Z_]{1,20}\Z")


class Reply(NamedTuple):
    command_id: str
    ok: bool
    brightness: object
    sound: object
    pir: object
    error: object


def validate_args(command, args):
    if command not in COMMANDS or len(args) != COMMANDS[command]:
        raise ValueError("Invalid command or argument count")
    if command in ("SET_LED", "SET_OUTPUT") and (type(args[0]) is not int or not 0 <= args[0] <= 100):
        raise ValueError("Expected LED brightness in 0–100")
    if command in ("PLAY_SOUND", "SET_OUTPUT") and args[-1] not in SOUNDS:
        raise ValueError("Invalid sound")


def encode(command_id, command, *args):
    if not IDENTIFIER.fullmatch(command_id):
        raise ValueError("Invalid command ID")
    validate_args(command, args)
    return (" ".join([VERSION, command_id, command] + [str(arg) for arg in args]) + "\n").encode("ascii")


def parse_reply(line):
    if not line or len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise ValueError("Invalid response length")
    fields = line.decode("ascii").split()
    if len(fields) < 3 or fields[0] != VERSION or not IDENTIFIER.fullmatch(fields[1]):
        raise ValueError("Invalid response prefix")
    _, command_id, kind = fields[:3]
    if kind == "NACK" and len(fields) == 4 and CODE.fullmatch(fields[3]):
        return Reply(command_id, False, None, None, None, fields[3])
    if kind == "ACK" and len(fields) == 6:
        brightness, sound, pir = fields[3:]
        if brightness.isdigit() and 0 <= int(brightness) <= 100 and sound in SOUNDS and pir in ("0", "1", "-"):
            return Reply(command_id, True, int(brightness), sound, None if pir == "-" else pir == "1", None)
    raise ValueError("Invalid response fields")
