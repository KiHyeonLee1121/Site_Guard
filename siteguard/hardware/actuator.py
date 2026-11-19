"""Output ID assignment and mock/physical actuator contracts."""

import random


class CommandIDs:
    def __init__(self):
        self.value = random.SystemRandom().randrange(1 << 32)

    def next(self):
        self.value = (self.value + 1) % (1 << 32)
        return "{:08X}".format(self.value)
