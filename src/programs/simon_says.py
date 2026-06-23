"""SimonSays: a "repeat the growing pattern" memory game.

The box plays a pattern on the front-row lasers (ports 0..5), one lit step at a
time with an ascending-kick tone per step. The player repeats it by pressing the
matching buttons. Each cleared round appends one new random step (classic Simon:
the existing prefix is kept) until the pattern reaches
``config.SimonSays.WIN_LENGTH`` steps, at which point the player wins.

Mistakes are forgiving: the player has ``config.SimonSays.LIVES`` lives, shown on
the back-row "life" lasers. A wrong press costs a life and replays the *same*
round; running out of lives plays a "game over" line and restarts from length 1
(lives refilled). Reachable from the operator menu (GameSelect slot 5) or via
``python -m src -s -p SimonSays``.
"""
import os
import random

from .base import *
from ..event_loop import *
from ..config import config
from ..animation import random_k_dance


class SimonSays(Program):
    """Repeat-the-pattern memory game on the front-row lasers."""

    # Voice / sfx asset paths (relative to assets/sounds/effects).
    WELCOME = os.path.join("simon", "welcome.wav")
    WIN_VOICE = os.path.join("simon", "win.wav")
    GAMEOVER_VOICE = os.path.join("simon", "game_over.wav")
    BUZZ = os.path.join("simon", "buzz.wav")
    HOORAY = os.path.join("positive", "hooray.wav")
    # mistake_{remaining}.wav lines, keyed by how many lives are left after a miss.
    MISTAKE_VOICE = {n: os.path.join("simon", f"mistake_{n}.wav")
                     for n in range(1, config.SimonSays.LIVES)}
    # Random affirmation played when a round is cleared, to mark the hand-off
    # between the player's turn and the next demo.
    AFFIRM_VOICES = [os.path.join("simon", f"{w}.wav")
                     for w in ("good", "nice", "swell")]

    ECHO_COOLDOWN_MS = 120   # debounce so a bouncing button doesn't double-fire

    def __init__(self):
        super().__init__()

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        """Load audio and (re)initialise all run state. May be called many times."""
        cfg = config.SimonSays
        self.play_buttons = list(cfg.PLAY_BUTTONS)
        self.win_length = cfg.WIN_LENGTH
        self.max_lives = cfg.LIVES
        self.on_ms = cfg.ON_MS
        self.gap_ms = cfg.GAP_MS
        self.cheer_ms = cfg.CHEER_MS
        self.idle_ms = cfg.IDLE_MS

        # Audio: ascending kicks per step, plus spoken/buzzer feedback. Loaded in
        # start() (not __init__) so it is valid against the current mixer.
        self.game.mixer.use_patch(cfg.PATCH)
        for name in (self.WELCOME, self.WIN_VOICE, self.GAMEOVER_VOICE,
                     self.BUZZ, self.HOORAY, *self.MISTAKE_VOICE.values(),
                     *self.AFFIRM_VOICES):
            self.game.mixer.load_effect(name)

        # Run state: reset everything since start() may run more than once.
        self.pattern = []
        self.input_index = 0
        self.lives = self.max_lives
        self.accepting_input = False
        self.awaiting_start = True
        self.last_activity_ms = 0
        self._clock_ms = 0

        self.game.lasers.set_word(0)
        self.game.mixer.play_effect(self.WELCOME)

    def quit(self):
        """Clear the lasers and hand control back to the state machine."""
        self.game.lasers.set_word(0)
        super().quit()

    # -- per-frame update ---------------------------------------------------
    def update(self, dt):
        """Drain input and nudge a stalled player by re-showing the pattern."""
        super().update(dt)
        self._clock_ms += dt

        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self._on_button_down(event.key)
            elif event.type == EventType.BUTTON_UP:
                self._on_button_up(event.key)

        # Gentle nudge: re-demonstrate (no life lost) if the player stalls.
        if (self.accepting_input
                and self._clock_ms - self.last_activity_ms > self.idle_ms):
            self.play_pattern()

    # -- input --------------------------------------------------------------
    def _on_button_down(self, button_id):
        if button_id not in self.play_buttons:
            return
        if self.awaiting_start:
            self.awaiting_start = False
            return self.begin_game()
        if not self.accepting_input:
            return  # ignore presses while the box is demonstrating
        self.last_activity_ms = self._clock_ms
        self._echo(button_id)
        if button_id == self.pattern[self.input_index]:
            self.input_index += 1
            if self.input_index == len(self.pattern):
                self.round_cleared()
        else:
            self.mistake()

    def _on_button_up(self, button_id):
        if button_id in self.play_buttons:
            self.game.lasers.turn_off(button_id)

    def _echo(self, button_id):
        """Light + sound the pressed laser (rate-limited against bounce)."""
        self.game.lasers.turn_on(button_id)
        if button_id not in self.cooldowns:
            self.game.mixer.play_by_id(button_id, duck=False)
            self.start_cooldown(button_id, ms=self.ECHO_COOLDOWN_MS)

    # -- game flow ----------------------------------------------------------
    def begin_game(self):
        """First press: refill lives, seed a length-1 pattern, and demo it."""
        self.lives = self.max_lives
        self.pattern = [random.choice(self.play_buttons)]
        self.play_pattern()

    def play_pattern(self):
        """Demonstrate the current pattern, then hand the turn to the player."""
        self.accepting_input = False
        self.input_index = 0
        self._clear_play_lasers()
        step_ms = self.on_ms + self.gap_ms
        for k, step in enumerate(self.pattern):
            self.after(k * step_ms, self._show_step, step)
            self.after(k * step_ms + self.on_ms, self._hide_step, step)
        self.after(len(self.pattern) * step_ms + 250, self._start_input)

    def _show_step(self, step):
        self.game.lasers.turn_on(step)
        self.game.mixer.play_by_id(step, duck=False)

    def _hide_step(self, step):
        self.game.lasers.turn_off(step)

    def _start_input(self):
        self._clear_play_lasers()
        self.accepting_input = True
        self.input_index = 0
        self.last_activity_ms = self._clock_ms

    def round_cleared(self):
        """Player nailed the round: win at WIN_LENGTH, else grow and replay.

        The laser lit by the final correct press is intentionally left on (it is
        cleared on button-up, or by the next demo's :meth:`play_pattern`) so the
        last step gives the same visual feedback as every other press.
        """
        self.accepting_input = False
        if len(self.pattern) >= self.win_length:
            return self.win()
        # Random "Good!/Nice!/Swell!" marks the end of the player's turn before
        # the next demo begins.
        self.game.mixer.play_effect(random.choice(self.AFFIRM_VOICES))
        self.after(self.cheer_ms, self._grow_and_replay)

    def _grow_and_replay(self):
        self.pattern.append(random.choice(self.play_buttons))
        self.play_pattern()

    def mistake(self):
        """Wrong press: buzz + flash, lose a life, then retry or game over."""
        self.accepting_input = False
        self.lives -= 1
        self.game.mixer.play_effect(self.BUZZ)
        self._flash_play_lasers()
        if self.lives <= 0:
            self.after(900, self.game_over)
        else:
            self.after(300, self.game.mixer.play_effect, self.MISTAKE_VOICE[self.lives])
            self.after(1600, self.play_pattern)  # retry the SAME round

    def game_over(self):
        """Out of lives: announce, refill, and restart from length 1."""
        self.game.mixer.play_effect(self.GAMEOVER_VOICE)
        self.lives = self.max_lives
        self.pattern = [random.choice(self.play_buttons)]
        self.after(1800, self.play_pattern)

    def win(self):
        """Reached WIN_LENGTH: celebrate, then quit back to the menu."""
        self.game.mixer.play_effect(self.HOORAY)
        self.after(300, self.game.mixer.play_effect, self.WIN_VOICE)
        random_k_dance(k=3, fps=8, dur=2.5).start()
        self.after(3200, self.quit)

    # -- laser helpers ------------------------------------------------------
    def _clear_play_lasers(self):
        for b in self.play_buttons:
            self.game.lasers.turn_off(b)

    def _flash_play_lasers(self, times=3, period_ms=140):
        """Blink the whole play row a few times (the mistake "error" flash)."""
        for n in range(times):
            self.after(n * period_ms, self._set_play_lasers, True)
            self.after(n * period_ms + period_ms // 2, self._set_play_lasers, False)

    def _set_play_lasers(self, on):
        for b in self.play_buttons:
            self.game.lasers.set_value(b, 1 if on else 0)


# Instantiate once at import so it registers with the StateMachine.
SimonSays()
