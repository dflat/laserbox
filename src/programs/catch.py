"""Catch: a reaction-timing climb across four speed levels on a moving target.

Play happens on the left/black half of the row only -- ports ``0..6`` -- with a
fresh random target each round. Phases:

* **READY** -- a short spoken intro explains the rules while only the target
  laser blinks (at ``config.Catch.BLINK_HZ``, twice a second). Level 1 then
  starts on its own when the intro finishes; pressing any button skips the rest
  of the intro and starts level 1 immediately.
* **CHASE** -- a single laser "blip" spawns at port 0 and ping-pongs back and
  forth across the half (``0 -> 6 -> 0``) at the current level's speed. It keeps
  bouncing **forever** until the player presses. The target keeps blinking so the
  goal stays visible while the blip races past it.

Each round picks a new random target from ``config.Catch.TARGET_PORTS`` (held lit
during the pre-chase pause as a preview), so the spot you are aiming for moves
from round to round.

Pressing **any** button during the chase stops the blip and resolves the round
by where it is at that instant:

* **Catch** -- blip on the target. The player climbs to the next, faster level
  (announced by voice). Catching on the final (fourth) level wins the whole game
  with a Golf-style celebration, then returns to the menu.
* **Miss** -- blip anywhere else. A failure line plays and the player drops back
  to level 1.

Speed escalates **per success across the session**, not within one chase: each
level in ``config.Catch.LEVEL_STEP_MS`` is faster than the last. Reachable from
the operator menu (GameSelect slot 7) or via ``python -m src -s -p Catch``.
"""
import random

from .base import *
from ..event_loop import *
from ..config import config
from ..animation import random_k_dance


class Catch(Program):
    """Climb four increasingly fast levels by catching the bouncing blip."""

    # Phase names (also referenced by the headless test).
    READY = "READY"          # intro / target preview; auto-advances or skip w/ a press
    CHASE = "CHASE"
    PAUSE = "PAUSE"          # frozen between levels / during the win dance
    MISS_HOLD = "MISS_HOLD"  # showing where the player missed before the reset

    def __init__(self):
        # Registers this singleton and sets up tick/scheduler/cooldowns. Static
        # data only here -- self.game does not exist until make_active_program.
        super().__init__()

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        """Load audio, play the intro, then auto-start level 1. May run many times."""
        cfg = config.Catch
        self.target_ports = tuple(cfg.TARGET_PORTS)
        self.target = random.choice(self.target_ports)  # READY preview; re-rolled per round
        self.last_port = cfg.N_PORTS - 1
        self.level_step_ms = tuple(cfg.LEVEL_STEP_MS)
        self.level_sounds = tuple(cfg.LEVEL_SOUNDS)
        self.level_advance_ms = cfg.LEVEL_ADVANCE_MS
        self.miss_reset_ms = cfg.MISS_RESET_MS
        self.intro_sound = cfg.INTRO_SOUND
        self.miss_sound = cfg.MISS_SOUND
        self.win_sound = cfg.WIN_SOUND
        # Half a blink cycle: BLINK_HZ flashes/sec => on this long, off this long.
        self.blink_half_period_ms = 1000 / (2 * cfg.BLINK_HZ)

        # Load effects in start() (not __init__) so they stay valid against the
        # current mixer, which other programs may have re-initialised. The win
        # sound matches Golf's celebration volume.
        for name in (self.intro_sound, self.miss_sound, *self.level_sounds):
            self.game.mixer.load_effect(name)
        self.game.mixer.load_effect(self.win_sound, volume=config.CONGRATS_VOL)

        self.level_index = 0
        intro_ms = self.game.mixer.effects[self.intro_sound].get_length() * 1000
        self.game.mixer.play_effect(self.intro_sound)
        self._begin_ready(intro_ms)

    # -- phase transitions --------------------------------------------------
    def _begin_ready(self, delay_ms):
        """Blink the target through the intro, then drop straight into level 1."""
        self.state = self.READY
        self._clock_ms = 0.0  # restart the blink so it begins on a lit flash
        self.game.lasers.set_word(0)
        # Auto-start level 1 when the intro finishes; a press skips to it sooner.
        self.after(delay_ms, self._enter_level, 0)

    def _enter_level(self, level_index, announce=True):
        """Optionally announce ``level_index`` (the level-up = "nice catch" cue), hold, chase.

        ``announce`` is suppressed when re-arming at level 1 after a miss: the
        failure line already says we are back at level 1, so replaying the
        "level 1, here we go" cue every reset would be redundant.

        Each level is a fresh **round**, so a new random target is rolled here and
        held lit through the pause as a preview before the blip starts moving.
        """
        self.level_index = level_index
        self.target = random.choice(self.target_ports)  # new target each round
        self.state = self.PAUSE
        self.game.lasers.set_word(1 << self.target)  # hold target lit during the cue
        if announce:
            self.game.mixer.play_effect(self.level_sounds[level_index])
        self.after(self.level_advance_ms, self._start_chase)

    def _start_chase(self):
        """Spawn the bouncing blip at port 0 for the current level's speed."""
        self.state = self.CHASE
        self.blip = 0
        self.blip_dir = 1
        self._blip_accum_ms = 0.0

    def _catch(self):
        """A successful catch: climb a level, or win if this was the last one."""
        if self.level_index >= len(self.level_step_ms) - 1:
            return self._win()
        self._enter_level(self.level_index + 1)

    def _miss(self):
        """A miss: hold the missed frame, play the failure line, then drop to L1.

        Holds the blip solid where the player pressed for the whole reset pause,
        while the target keeps blinking, so the player can both see how far off
        their timing was and still pick out the target before re-arming at L1.
        """
        self.state = self.MISS_HOLD  # blip frozen at self.blip; _render keeps it lit
        self.game.mixer.play_effect(self.miss_sound)
        self.after(self.miss_reset_ms, self._rearm)

    def _rearm(self):
        """Auto-restart at level 1 after the miss hold (no press to continue).

        Stays silent: the miss line already announced the drop back to level 1,
        so the "level 1, here we go" cue is only spoken once, at the very start.
        """
        self._enter_level(0, announce=False)

    def _win(self):
        """Won the final level: do what Golf does -- congrats + dance, then menu."""
        self.state = self.PAUSE
        dur = self.game.mixer.effects[self.win_sound].get_length()
        self.game.mixer.play_effect(self.win_sound)
        random_k_dance(k=3, fps=8, dur=max(0, dur - 1.2)).start()
        self.after(dur * 1000, self.quit)

    # -- per-frame update ---------------------------------------------------
    def update(self, dt):
        """Per-frame: judge presses against the shown blip, then advance/render."""
        super().update(dt)
        self._clock_ms += dt

        # Handle input first so a press is judged against the blip position the
        # player is actually looking at (this frame's render), not next step's.
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self._on_button_down(event.key)

        if self.state == self.CHASE:
            self._advance_blip(dt)
        if self.state in (self.READY, self.CHASE, self.MISS_HOLD):
            self._render()

    # -- blip motion --------------------------------------------------------
    def _advance_blip(self, dt):
        """Step the blip on the current level's clock; bounce forever 0<->13."""
        self._blip_accum_ms += dt
        step_ms = self.level_step_ms[self.level_index]
        while self._blip_accum_ms >= step_ms:
            self._blip_accum_ms -= step_ms
            self._step_blip()

    def _step_blip(self):
        """Move the blip one port, reflecting at either end."""
        self.blip += self.blip_dir
        if self.blip >= self.last_port:
            self.blip = self.last_port
            self.blip_dir = -1
        elif self.blip <= 0:
            self.blip = 0
            self.blip_dir = 1

    # -- input --------------------------------------------------------------
    def _on_button_down(self, button_id):
        """Resolve a press: skip the intro in READY, judge the blip in CHASE.

        Any button counts -- the player just has to stop the blip on the target,
        not hit the target's own button -- so a press is a catch whenever the
        blip is on the target and a miss anywhere else. Presses in the between-
        level pauses are ignored.
        """
        if self.state == self.READY:
            return self._skip_intro()
        if self.state != self.CHASE:
            return
        if self.blip == self.target:
            self._catch()
        else:
            self._miss()

    def _skip_intro(self):
        """A press during the intro: cut the narration short and start level 1 now."""
        self.scheduler = []  # drop the pending intro -> level-1 transition
        self.game.mixer.effects[self.intro_sound].stop()
        self._enter_level(0)

    # -- rendering ----------------------------------------------------------
    def _blink_on(self):
        """Whether the target should be lit this frame (BLINK_HZ flashing)."""
        return int(self._clock_ms // self.blink_half_period_ms) % 2 == 0

    def _render(self):
        """Compose the laser word: the blinking target plus the blip.

        The target blinks in every rendered phase. The blip is drawn solid both
        while chasing and while held at a miss (so the missed press stays visible
        against the still-blinking target).
        """
        word = self._blink_on() << self.target
        if self.state in (self.CHASE, self.MISS_HOLD):
            word |= 1 << self.blip
        self.game.lasers.set_word(word)


# Instantiate once at import so it registers with the StateMachine.
Catch()
