from .base import *
from ..event_loop import *
from collections import deque

class TogglePattern(Program):
    HISTORY_SIZE = 12

    def __init__(self):
        super().__init__()

    def start(self, start_audio=None, toggle_pattern=None, hold_animation: 'Animation'=None):
        self.start_audio = start_audio
        self.pattern = toggle_pattern
        self.hold_animation = hold_animation
        self.pattern_search_size = 2*len(toggle_pattern) - 1 #pattern_search_size
        self.game.mixer.load_music(start_audio, loops=0)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1
        self.toggle_history = deque(maxlen=self.HISTORY_SIZE)
        if self.hold_animation:
            print('starting hold anim')
            self.hold_animation.start()

    def check_for_toggle_success(self):
        target_index = 0
        for toggle_state in list(self.toggle_history)[-self.pattern_search_size:]:
            target_state = self.pattern[target_index]
            if toggle_state == target_state:
                target_index += 1
            if target_index == len(self.pattern):
                return True
        return False

    def quit(self):
        if self.hold_animation:
            self.hold_animation.kill()
        self.toggle_history = deque(maxlen=self.HISTORY_SIZE)
        super().quit()

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)

        # check event loop for input changes
        for event in events.get():
            if isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.toggle_history.append(toggle_state)
                print('toggles:', toggle_state)

                if self.check_for_toggle_success():
                    # move to next game
                    print('got correct toggle sequence.')
                    self.quit()

TogglePattern()