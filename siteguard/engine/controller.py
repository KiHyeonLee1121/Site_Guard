"""Only meaningful output changes cause a new actuator command."""

from collections import OrderedDict

from siteguard.schemas import OFF


class ActionController:
    def __init__(self, actuator):
        self.actuator = actuator
        self.current = OFF
        self.played = OrderedDict()

    def apply(self, output):
        if output == self.current:
            return None
        self.current = output
        play = output.level > 0 and output.sound_revision not in self.played
        if play:
            self.played[output.sound_revision] = None
            if len(self.played) > 256:
                self.played.popitem(last=False)
        return self.actuator.submit(output, play=play)

    def reset(self):
        return self.apply(OFF)
