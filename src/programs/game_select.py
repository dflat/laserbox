from .base import *
from ..event_loop import *
from ..config import config
import os
import sys
import subprocess
import pygame


class GameSelect(Program):
    """
    Operator-facing selection menu and system "home". The box boots here, and
    every launched game/composition returns here when it finishes (or when the
    entry gesture is performed mid-game).

    **Game slots** (``config.GameSelect.MENU``) -- one per assigned button:

    * first press announces the entry's name and "arms" it (its laser lights),
    * pressing the same button again launches it,
    * pressing a different assigned button re-arms to that one,
    * an armed selection clears itself after ``ARM_TIMEOUT_MS``.

    **System slots** (``config.GameSelect.SYSTEM_MENU``, the last two buttons)
    reboot or shut the box down. Because that is destructive they use a
    *three-press* confirm flow:

    * first press announces ("reboot"/"shutdown") and lights the slot,
    * second press arms it (lights every laser, plays the confirm prompt),
    * third press executes the action,
    * pressing *any other button* while a system slot is armed cancels it and
      returns to the menu; it also expires after ``ARM_TIMEOUT_MS``.

    Unassigned buttons are ignored.
    """
    EFFECT_DIR = 'menu'
    STD_FREQ = 22050
    STD_FORMAT = -16
    STD_CHANNELS = 1
    ALL_LASERS = (1 << 14) - 1  # every laser on -- the "armed to fire" signal

    def __init__(self):
        super().__init__()
        self.menu = config.GameSelect.MENU
        self.system_menu = config.GameSelect.SYSTEM_MENU
        self.system_actions = config.GameSelect.SYSTEM_ACTIONS
        self.choose_sound = os.path.join(self.EFFECT_DIR, 'choose_a_game.wav')

    def start(self):
        self._ensure_standard_mixer()
        self.armed = None         # button_id currently armed, or None
        self.arm_deadline = None  # tick at which the arm expires
        self.press_count = 0      # presses on the armed slot so far
        self.power_committed = False  # a reboot/shutdown has been issued
        self.arm_timeout_ticks = int(
            config.FPS * config.GameSelect.ARM_TIMEOUT_MS / 1000)
        self.game.lasers.set_word(0)
        self._load_effects()
        self._play(self.choose_sound)

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
        # (re)load fresh so the Sounds are valid against the current mixer.
        # Tolerant of missing files: a missing announcement must never stop the
        # menu (the box's home screen) from starting.
        self._load(self.choose_sound)
        for target, announce in self.menu.values():
            self._load(self._effect_path(announce))
        for spec in self.system_menu.values():
            self._load(self._effect_path(spec['announce']))
            self._load(self._effect_path(spec['confirm']))

    def _load(self, path):
        try:
            self.game.mixer.load_effect(path)
        except Exception as e:
            print(f'[GameSelect] could not load effect {path!r}: {e}')

    def _play(self, path):
        try:
            self.game.mixer.play_effect(path)
        except Exception as e:
            print(f'[GameSelect] could not play effect {path!r}: {e}')

    def _announce_file(self, button_id):
        """The name announcement for a slot (game or system)."""
        if button_id in self.system_menu:
            return self.system_menu[button_id]['announce']
        return self.menu[button_id][1]

    def _is_slot(self, button_id):
        return button_id in self.menu or button_id in self.system_menu

    def _arm(self, button_id):
        """First press of a slot: announce it and light its laser."""
        self.armed = button_id
        self.press_count = 1
        self.arm_deadline = self.tick + self.arm_timeout_ticks
        self.game.lasers.set_word(1 << button_id)  # light the armed slot
        self._play(self._effect_path(self._announce_file(button_id)))

    def _disarm(self):
        self.armed = None
        self.arm_deadline = None
        self.press_count = 0
        self.game.lasers.set_word(0)

    def _advance(self, button_id):
        """Repeat press of the already-armed slot.

        Game slots launch on the second press. System slots need a third press:
        the second arms them (all lasers + confirm prompt), the third executes.
        """
        self.press_count += 1
        self.arm_deadline = self.tick + self.arm_timeout_ticks  # keep alive

        if button_id not in self.system_menu:
            self._launch(button_id)            # game slot: second press launches
            return
        if self.press_count == 2:
            self.game.lasers.set_word(self.ALL_LASERS)  # unmistakable "armed"
            self._play(self._effect_path(self.system_menu[button_id]['confirm']))
        else:                                  # third (or later) press: execute
            self._execute_system_action(button_id)

    def _launch(self, button_id):
        target, announce = self.menu[button_id]
        self.game.state_machine.launch_context(target)

    def _execute_system_action(self, button_id):
        """Fire the reboot/shutdown command (no-op under the simulator)."""
        action = self.system_menu[button_id]['action']
        argv = self.system_actions[action]
        self.game.lasers.set_word(self.ALL_LASERS)
        self.power_committed = True            # ignore all further input
        if '-s' in sys.argv:
            print(f'[GameSelect] SIMULATED system action {action!r}: {argv}')
            return
        print(f'[GameSelect] executing system action {action!r}: {argv}')
        try:
            # Fire-and-forget: systemd then SIGTERMs us and game_loop's handler
            # clears lasers/audio/GPIO. (Verified: passwordless sudo on the box.)
            subprocess.Popen(argv)
        except Exception as e:
            print(f'[GameSelect] system action {action!r} failed: {e}')
            self.power_committed = False
            self._disarm()

    def update(self, dt):
        super().update(dt)

        if self.power_committed:
            return  # committed to reboot/shutdown; ignore input until we're stopped

        # expire a stale armed selection
        if self.armed is not None and self.tick > self.arm_deadline:
            self._disarm()

        for event in events.get():
            if event.type != EventType.BUTTON_DOWN:
                continue
            button_id = event.key

            if button_id == self.armed:
                is_game = button_id in self.menu
                self._advance(button_id)
                # a launched game tears GameSelect down; a committed power action
                # means we're shutting down -- either way, stop processing.
                if is_game or self.power_committed:
                    return
                continue

            # a different button was pressed
            if self.armed in self.system_menu:
                self._disarm()      # any other button cancels a pending power action
                continue
            if not self._is_slot(button_id):
                continue            # unassigned -> no-op
            self._arm(button_id)


GameSelect()
