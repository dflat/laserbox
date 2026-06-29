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
    * third press executes the action (after a spoken "rebooting/shutting down
      now" confirmation),
    * pressing *any other button* while a system slot is armed cancels it; if
      that button is itself a menu slot it then arms normally (announces its
      name), exactly like the rest of the menu. The arm also expires after
      ``ARM_TIMEOUT_MS``.

    Any button press while a system slot's (long) confirm prompt is still
    speaking cuts it short, so a quick confirm/cancel isn't talked over.

    **Volume slots** (``config.GameSelect.VOLUME_MENU``, buttons 10/11) are the
    other half of the system-control group. Each press is an instant ±10% step of
    the OS master volume (no arm/confirm): it lights a laser bar of the new level
    for a moment and speaks a live-preview confirmation *at the new level*, so the
    loudness itself previews the change. They act independently of any armed
    selection. (Volume is menu-only; during a game buttons 10/11 are ordinary
    game inputs.)

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
        # Volume slots (buttons 10/11) -- see class docstring.
        self.volume_menu = config.GameSelect.VOLUME_MENU
        self.volume_bar_ports = config.GameSelect.VOLUME_BAR_PORTS
        self.volume_bar_ms = config.GameSelect.VOLUME_BAR_MS
        self.vol_up = config.GameSelect.VOLUME_UP
        self.vol_down = config.GameSelect.VOLUME_DOWN
        self.vol_max = config.GameSelect.VOLUME_MAX
        self.vol_muted = config.GameSelect.VOLUME_MUTED

    def start(self):
        self._ensure_standard_mixer()
        self.armed = None         # button_id currently armed, or None
        self.arm_deadline = None  # now_ms at which the arm expires
        self.press_count = 0      # presses on the armed slot so far
        self.power_committed = False  # a reboot/shutdown has been issued
        self.arm_timeout_ms = config.GameSelect.ARM_TIMEOUT_MS
        self.bar_deadline = None  # now_ms at which the volume bar clears, or None
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
            self._load(self._effect_path(spec['execute']))
        for name in (self.vol_up, self.vol_down, self.vol_max, self.vol_muted):
            self._load(self._effect_path(name))

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

    def _stop_voice(self):
        """Cut any in-progress announcement short.

        GameSelect only ever plays one-shot voice effects (no music stream), so
        stopping every channel just silences the current spoken line -- used to
        keep the long confirm prompt from talking over a quick confirm/cancel.
        """
        try:
            pygame.mixer.stop()
        except Exception as e:
            print(f'[GameSelect] could not stop audio: {e}')

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
        self.arm_deadline = self.now_ms + self.arm_timeout_ms
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
        self.arm_deadline = self.now_ms + self.arm_timeout_ms  # keep alive

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
        spec = self.system_menu[button_id]
        action = spec['action']
        argv = self.system_actions[action]
        self.game.lasers.set_word(self.ALL_LASERS)
        self.power_committed = True            # ignore all further input

        # Audible "rebooting/shutting down now" confirmation. The caller has
        # already cut the confirm prompt short, so this won't overlap.
        execute_file = self._effect_path(spec['execute'])
        self._play(execute_file)

        if '-s' in sys.argv:
            print(f'[GameSelect] SIMULATED system action {action!r}: {argv}')
            return
        print(f'[GameSelect] executing system action {action!r}: {argv}')
        try:
            # Let the spoken confirmation finish before we issue the command:
            # systemd then SIGTERMs us and game_loop's handler silences audio,
            # which would otherwise clip "rebooting/shutting down now" mid-word.
            self._wait_for_effect(execute_file)
            # Fire-and-forget. (Verified: passwordless sudo on the box.)
            subprocess.Popen(argv)
        except Exception as e:
            print(f'[GameSelect] system action {action!r} failed: {e}')
            self.power_committed = False
            self._disarm()

    def _wait_for_effect(self, path):
        """Block until a just-played effect finishes (best effort).

        Used only on the real box, right before issuing a power command, so the
        spoken confirmation is heard in full before audio is torn down. Bounded
        by the clip's own length so a stuck channel can't hang the box.
        """
        sound = self.game.mixer.effects.get(path)
        if sound is None:
            return
        pygame.time.wait(int(sound.get_length() * 1000) + 100)

    # -- volume -------------------------------------------------------------
    def _effect_len(self, filename):
        """Length (s) of a loaded menu effect, or 0 if it never loaded."""
        sound = self.game.mixer.effects.get(self._effect_path(filename))
        return sound.get_length() if sound else 0.0

    def _volume_bar_word(self):
        """Laser word for the current volume, as a left->right bar.

        Lights a count of the 12 in-line ports proportional to the level (the two
        endcap ports are skipped, see ``VOLUME_BAR_PORTS``): none at muted, all 12
        at max.
        """
        ports = self.volume_bar_ports
        lit = round(self.game.volume.fraction * len(ports))
        return sum(1 << ports[i] for i in range(lit))

    def _base_laser_word(self):
        """The laser word to restore once the volume bar's dwell time is up.

        Re-derives what the lasers *should* show from the current arm state, so
        the temporary bar doesn't clobber an armed slot's lit laser.
        """
        if self.armed is None:
            return 0
        if self.armed in self.system_menu and self.press_count >= 2:
            return self.ALL_LASERS  # a power slot mid-confirm lights everything
        return 1 << self.armed

    def _adjust_volume(self, button_id):
        """Step the OS master volume and give bar + spoken-preview feedback.

        Up/down steps apply to the OS first, then speak at the new level so the
        loudness previews the change. The one exception is stepping to mute: the
        sink would be silent, so we speak "volume muted" at the still-audible
        level *first* and defer the actual OS mute until just after the line.
        """
        vol = self.game.volume
        direction = self.volume_menu[button_id]
        self._stop_voice()  # cut any prior preview so rapid presses don't stack

        if direction > 0:
            vol.step_up()
            clip = self.vol_max if vol.is_max else self.vol_up
            self._play(self._effect_path(clip))
        elif vol.peek_down() <= vol.min:
            # stepping to mute: announce audibly now, silence the OS after the line
            self._play(self._effect_path(self.vol_muted))
            vol.step_down(apply_os=False)  # record/show 0 now; OS muted shortly
            self.after(int(self._effect_len(self.vol_muted) * 1000) + 50, vol.apply)
        else:
            vol.step_down()
            self._play(self._effect_path(self.vol_down))

        # Flash the new level as a laser bar for a moment, then restore the base.
        self.game.lasers.set_word(self._volume_bar_word())
        self.bar_deadline = self.now_ms + self.volume_bar_ms

    def update(self, dt):
        super().update(dt)

        if self.power_committed:
            return  # committed to reboot/shutdown; ignore input until we're stopped

        # clear the volume bar once its dwell time is up, restoring the base display
        if self.bar_deadline is not None and self.now_ms > self.bar_deadline:
            self.bar_deadline = None
            self.game.lasers.set_word(self._base_laser_word())

        # expire a stale armed selection
        if self.armed is not None and self.now_ms > self.arm_deadline:
            self._disarm()

        for event in events.get():
            if event.type != EventType.BUTTON_DOWN:
                continue
            button_id = event.key

            # Volume buttons act immediately and independently of any armed
            # selection (no arm/confirm) -- handle them before the arm logic.
            if button_id in self.volume_menu:
                self._adjust_volume(button_id)
                continue

            # While a power slot is armed its (long) confirm prompt may still be
            # speaking; any press -- confirm or cancel -- cuts it short so it
            # doesn't talk over what happens next.
            if self.armed in self.system_menu:
                self._stop_voice()

            if button_id == self.armed:
                is_game = button_id in self.menu
                self._advance(button_id)
                # a launched game tears GameSelect down; a committed power action
                # means we're shutting down -- either way, stop processing.
                if is_game or self.power_committed:
                    return
                continue

            # A different button was pressed. If a power slot was armed, this
            # cancels it; then fall through so the new button arms normally
            # (announcing its name) when it is itself a menu slot.
            if self.armed in self.system_menu:
                self._disarm()
            if not self._is_slot(button_id):
                continue            # unassigned -> no-op
            self._arm(button_id)


GameSelect()
