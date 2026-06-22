from .base import *
from ..event_loop import *
from ..config import config
import os
import pygame


class GameSelect(Program):
    """
    Operator-facing selection menu and system "home". The box boots here, and
    every launched game/composition returns here when it finishes (or when the
    entry gesture is performed mid-game).

    Each assigned button (``config.GameSelect.MENU``) is a menu slot:

    * first press announces the entry's name and "arms" it (its laser lights),
    * pressing the same button again launches it,
    * pressing a different assigned button re-arms to that one,
    * an armed selection clears itself after ``ARM_TIMEOUT_MS``.

    Unassigned buttons are ignored.
    """
    EFFECT_DIR = 'menu'
    STD_FREQ = 22050
    STD_FORMAT = -16
    STD_CHANNELS = 1

    def __init__(self):
        super().__init__()
        self.menu = config.GameSelect.MENU
        self.choose_sound = os.path.join(self.EFFECT_DIR, 'choose_a_game.wav')

    def start(self):
        self._ensure_standard_mixer()
        self.armed = None         # button_id currently armed, or None
        self.arm_deadline = None  # tick at which the arm expires
        self.arm_timeout_ticks = int(
            config.FPS * config.GameSelect.ARM_TIMEOUT_MS / 1000)
        self.game.lasers.set_word(0)
        self._load_effects()
        self.game.mixer.play_effect(self.choose_sound)

    def _ensure_standard_mixer(self):
        """
        A program (e.g. MusicMaker) may have re-init'd pygame.mixer, invalidating
        cached Sound objects. If the mixer isn't at our standard config, reset it
        and drop the stale Sound caches so everything reloads cleanly.
        """
        init = pygame.mixer.get_init()
        want = (self.STD_FREQ, self.STD_FORMAT, self.STD_CHANNELS)
        if init is None or tuple(init[:3]) != want:
            pygame.mixer.quit()
            pygame.mixer.init(self.STD_FREQ, self.STD_FORMAT,
                              self.STD_CHANNELS, config.AUDIO_BUFFER)
            self.game.mixer.effects = {}
            self.game.mixer.patches = {}

    def _effect_path(self, filename):
        return os.path.join(self.EFFECT_DIR, filename)

    def _load_effects(self):
        # (re)load fresh so the Sounds are valid against the current mixer
        self.game.mixer.load_effect(self.choose_sound)
        for target, announce in self.menu.values():
            self.game.mixer.load_effect(self._effect_path(announce))

    def _announce(self, button_id):
        target, announce = self.menu[button_id]
        self.game.mixer.play_effect(self._effect_path(announce))

    def _arm(self, button_id):
        self.armed = button_id
        self.arm_deadline = self.tick + self.arm_timeout_ticks
        self.game.lasers.set_word(1 << button_id)  # light the armed slot
        self._announce(button_id)

    def _disarm(self):
        self.armed = None
        self.arm_deadline = None
        self.game.lasers.set_word(0)

    def _launch(self, button_id):
        target, announce = self.menu[button_id]
        self.game.state_machine.launch_context(target)

    def update(self, dt):
        super().update(dt)

        # expire a stale armed selection
        if self.armed is not None and self.tick > self.arm_deadline:
            self._disarm()

        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                button_id = event.key
                if button_id not in self.menu:
                    continue  # unassigned -> no-op
                if self.armed == button_id:
                    self._launch(button_id)
                    return  # GameSelect has been torn down; stop processing
                self._arm(button_id)


GameSelect()
