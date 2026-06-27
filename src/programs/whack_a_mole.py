"""WhackAMole: a timed reaction game where lit lasers are "moles" to whack.

Laser ``n`` is hole ``n`` and button ``n`` is its mallet (the same 1:1 mapping
SimonSays uses to echo presses). A "mole" is a lit laser that pops up at a random
port and stays lit for a shrinking lifetime; pressing its button while lit is a
**hit**, letting it time out is a **miss**. The game runs for a fixed timed round
and gets harder as it goes (moles spawn faster and live shorter).

Two modes, chosen at the start by *which* button you press to begin:

* **1-player** -- press any **black** button (ports 0-6). Moles only appear on the
  left half; you chase your own high score.
* **2-player** -- press any **white** button (ports 7-13). Moles appear on both
  halves; the left half (0-6) is player 1, the right half (7-13) is player 2
  (socially enforced -- the box can't tell who is pressing). Spawns are balanced
  so each half gets an **equal number of moles**, and whichever half has whacked
  more when the buzzer sounds wins.

The intro prompt is skippable, exactly like SimonSays' welcome: making a selection
before the spoken prompt finishes starts the round immediately. Reachable from the
operator menu (GameSelect slot 8) or via ``python -m src -s -p WhackAMole``.
"""
import random

from .base import *
from ..event_loop import *
from ..config import config
from ..animation import random_k_dance


def _lerp(t, a, b):
    """Linear interpolation: ``a`` at ``t=0``, ``b`` at ``t=1`` (``t`` is clamped)."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return a + t * (b - a)


class WhackAMole(Program):
    """Timed whack-a-mole on the laser row, single- or two-player."""

    # Phase names (also referenced by the headless test).
    READY = "READY"     # intro prompt; waiting for a black/white button to pick mode
    PLAY = "PLAY"       # moles spawning; the timed round
    RESULT = "RESULT"   # round over: winner display + celebration, then quit

    ALL_WORD = (1 << 14) - 1  # every laser on (tie display)

    def __init__(self):
        # Registers this singleton; static data only (self.game does not exist yet).
        super().__init__()

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        """Load audio, then show the (skippable) mode-select prompt. May run many times."""
        cfg = config.WhackAMole
        self.left_ports = tuple(cfg.LEFT_PORTS)
        self.right_ports = tuple(cfg.RIGHT_PORTS)
        self.round_ms = cfg.ROUND_MS
        self.spawn_ms_start = cfg.SPAWN_MS_START
        self.spawn_ms_end = cfg.SPAWN_MS_END
        self.lifetime_ms_start = cfg.LIFETIME_MS_START
        self.lifetime_ms_end = cfg.LIFETIME_MS_END
        self.max_per_side = cfg.MAX_PER_SIDE
        self.warn_ms = cfg.WARN_MS
        self.blink_half_ms = cfg.BLINK_HALF_MS
        self.prompt_half_ms = cfg.PROMPT_HALF_MS

        self.popup = cfg.POPUP
        self.hammer = cfg.HAMMER
        self.mole_hit = cfg.MOLE_HIT
        self.welcome = cfg.WELCOME
        self.result_single = cfg.RESULT_SINGLE
        self.p1_wins = cfg.P1_WINS
        self.p2_wins = cfg.P2_WINS
        self.tie = cfg.TIE
        self.congrats = cfg.CONGRATS
        self.fallback_patch = cfg.FALLBACK_PATCH
        self.music = cfg.MUSIC

        # Sound effects, loaded in start() (not __init__) so the Sounds are valid
        # against the current mixer, which other programs may have re-initialised.
        # ``hammer`` fires on every press (the mallet swing), ``mole_hit`` only on a
        # successful whack, ``popup`` on each spawn. The spoken stubs + shared
        # celebration load defensively -- a missing wav is simply skipped at play.
        self._safe_load_effect(self.popup, volume=0.6)
        self._safe_load_effect(self.hammer, volume=0.7)
        self._safe_load_effect(self.mole_hit, volume=0.9)
        for name in (self.welcome, self.result_single, self.p1_wins,
                     self.p2_wins, self.tie):
            self._safe_load_effect(name)
        self._safe_load_effect(self.congrats, volume=config.CONGRATS_VOL)
        self._congrats_dur = (self.game.mixer.effects[self.congrats].get_length()
                              if self.congrats in self.game.mixer.effects else 3.0)
        # Fallback bonk if the hit folder is empty.
        try:
            self.game.mixer.use_patch(self.fallback_patch)
        except Exception as e:
            print(f"[WhackAMole] fallback patch unavailable: {e}")

        # Run state: reset everything since start() may run more than once.
        self.phase = self.READY
        self.mode = None                # 'single' | 'multi'
        self.sides = []                 # [(name, ports), ...]; set when mode is picked
        self.score = {}                 # side name -> hits
        self.spawn_count = {}           # side name -> total moles spawned (for balance)
        self.moles = {}                 # port -> remaining lifetime (ms)
        self._clock_ms = 0.0            # free-running clock for blink/prompt phases
        self._elapsed_ms = 0.0          # time into the current round
        self._spawn_accum = 0.0         # accumulator that triggers spawns
        self._result_word = None        # winner laser word held during RESULT (multi)
        self._dance_pending = False     # whether RESULT should run random_k_dance (single)

        self.game.lasers.set_word(0)
        self._safe_play_effect(self.welcome)  # spoken prompt; a press skips it

    def quit(self):
        """Clear the lasers and hand control back to the state machine."""
        self.game.lasers.set_word(0)
        super().quit()

    # -- per-frame update ---------------------------------------------------
    def update(self, dt):
        """Per-frame: judge presses, age/spawn moles during PLAY, then render."""
        super().update(dt)
        self._clock_ms += dt

        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self._on_button_down(event.key)

        if self.phase == self.PLAY:
            self._elapsed_ms += dt
            self._age_moles(dt)
            self._spawn(dt)

        self._render()

    # -- input --------------------------------------------------------------
    def _on_button_down(self, button_id):
        """Pick the mode in READY; whack in PLAY; ignore presses in RESULT."""
        if self.phase == self.READY:
            return self._select_mode(button_id)
        if self.phase != self.PLAY:
            return
        self._safe_play_effect(self.hammer)  # the mallet swings on *every* press
        if button_id in self.moles:
            self._hit(button_id)
        # An empty hole still swings the hammer but scores nothing (you can flail).

    def _select_mode(self, button_id):
        """A black button (left half) starts 1-player; a white button starts 2-player.

        Cuts the spoken prompt short, exactly like SimonSays' welcome.
        """
        if button_id in self.left_ports:
            self.mode = "single"
            self.sides = [("left", self.left_ports)]
        elif button_id in self.right_ports:
            self.mode = "multi"
            self.sides = [("left", self.left_ports), ("right", self.right_ports)]
        else:
            return  # not a play port (shouldn't happen: 0..13 are all covered)

        if self.welcome in self.game.mixer.effects:
            self.game.mixer.effects[self.welcome].stop()  # skip the rest of the prompt
        self._begin_play()

    def _hit(self, port):
        """Whack a live mole: score it to its half and play the mole-hit sound."""
        del self.moles[port]
        self.score[self._side_of(port)] += 1
        if self.mole_hit in self.game.mixer.effects:
            self._safe_play_effect(self.mole_hit)
        else:
            self.game.mixer.play_by_id(port, duck=False)  # pitched fallback bonk

    # -- round flow ---------------------------------------------------------
    def _begin_play(self):
        """Start the timed round: reset scores, prime a mole, schedule the buzzer."""
        self.score = {name: 0 for name, _ in self.sides}
        self.spawn_count = {name: 0 for name, _ in self.sides}
        self.moles = {}
        self._elapsed_ms = 0.0
        self._spawn_accum = 0.0
        self.phase = self.PLAY
        self._safe_load_music(self.music)
        for _ in self.sides:           # prime one mole per half so play starts at once
            self._try_spawn()
        self.after(self.round_ms, self._end_round)

    def _age_moles(self, dt):
        """Count down every mole; one that reaches zero has been missed (despawns)."""
        for port in list(self.moles):
            self.moles[port] -= dt
            if self.moles[port] <= 0:
                del self.moles[port]

    def _spawn(self, dt):
        """Spawn moles on the ramping cadence (faster as the round progresses)."""
        self._spawn_accum += dt
        interval = self._spawn_interval()
        while self._spawn_accum >= interval:
            self._spawn_accum -= interval
            self._try_spawn()
            interval = self._spawn_interval()  # the ramp may have moved it

    def _spawn_interval(self):
        """Ms between spawns right now. Split across halves so each sees the same rate.

        With two halves in play the box spawns twice as often (alternating to the
        half that is "behind"), giving each half the single-player spawn rate while
        keeping the per-half mole counts equal.
        """
        per_side = _lerp(self._elapsed_ms / self.round_ms,
                         self.spawn_ms_start, self.spawn_ms_end)
        return per_side / len(self.sides)

    def _current_lifetime_ms(self):
        """How long a freshly spawned mole stays lit right now (shrinks over the round)."""
        return _lerp(self._elapsed_ms / self.round_ms,
                     self.lifetime_ms_start, self.lifetime_ms_end)

    def _try_spawn(self):
        """Pop a mole on the half with the fewest spawns so far, keeping halves even.

        Always feeds the half that is "behind" on spawn count; if that half is full
        (``MAX_PER_SIDE`` moles already up) the spawn is skipped rather than handed
        to the other half, so the running counts stay balanced for fair scoring.
        """
        name, ports = min(self.sides, key=lambda s: self.spawn_count[s[0]])
        free = [p for p in ports if p not in self.moles]
        occupied = len(ports) - len(free)
        if not free or occupied >= self.max_per_side:
            return
        port = random.choice(free)
        self.moles[port] = self._current_lifetime_ms()
        self.spawn_count[name] += 1
        self._safe_play_effect(self.popup)

    def _end_round(self):
        """Buzzer: stop play, announce the result, celebrate, then quit."""
        self.phase = self.RESULT
        self.moles = {}
        self.game.mixer.fade_music(1500)
        self._result_word = None

        if self.mode == "single":
            vo = self.result_single
            self._dance_pending = True
        else:
            left, right = self.score["left"], self.score["right"]
            if left > right:
                vo, self._result_word = self.p1_wins, self._word(self.left_ports)
            elif right > left:
                vo, self._result_word = self.p2_wins, self._word(self.right_ports)
            else:
                vo, self._result_word = self.tie, self.ALL_WORD
            self._dance_pending = False

        # Speak the result first (if recorded), then fire the celebration so the
        # jingle does not talk over the announcement.
        delay = 0
        if vo in self.game.mixer.effects:
            self._safe_play_effect(vo)
            delay = int(self.game.mixer.effects[vo].get_length() * 1000) + 150
        self.after(delay, self._celebrate)
        self.after(delay + int(self._congrats_dur * 1000) + 400, self.quit)

    def _celebrate(self):
        """Play the shared celebration; in 1-player also run the laser dance."""
        if self._dance_pending:
            random_k_dance(k=3, fps=8, dur=max(0.0, self._congrats_dur - 1.2)).start()
        self._safe_play_effect(self.congrats)

    # -- rendering ----------------------------------------------------------
    def _render(self):
        """Drive the lasers for the current phase."""
        if self.phase == self.READY:
            self._render_prompt()
        elif self.phase == self.PLAY:
            self._render_moles()
        elif self.phase == self.RESULT and self._result_word is not None:
            self._render_result()
        # In RESULT with no winner word (single-player) random_k_dance owns the lasers.

    def _render_prompt(self):
        """Alternately light the black and white halves to invite a mode choice."""
        show_left = int(self._clock_ms // self.prompt_half_ms) % 2 == 0
        ports = self.left_ports if show_left else self.right_ports
        self.game.lasers.set_word(self._word(ports))

    def _render_moles(self):
        """Light every live mole; blink any in the final WARN_MS as a "leaving" cue."""
        word = 0
        blink_on = int(self._clock_ms // self.blink_half_ms) % 2 == 0
        for port, remaining in self.moles.items():
            if remaining < self.warn_ms and not blink_on:
                continue
            word |= 1 << port
        self.game.lasers.set_word(word)

    def _render_result(self):
        """Blink the winning half (or the whole row on a tie) during the celebration."""
        on = int(self._clock_ms // 250) % 2 == 0
        self.game.lasers.set_word(self._result_word if on else 0)

    # -- helpers ------------------------------------------------------------
    def _side_of(self, port):
        """Return the half name ('left'/'right') that owns ``port``."""
        return "left" if port in self.left_ports else "right"

    def _word(self, ports):
        """Build a laser word with every port in ``ports`` lit."""
        word = 0
        for p in ports:
            word |= 1 << p
        return word

    def _safe_load_effect(self, name, volume=1.0):
        """Load an effect, returning False (not raising) if the file is absent."""
        try:
            self.game.mixer.load_effect(name, volume=volume)
            return True
        except Exception as e:
            print(f"[WhackAMole] missing effect {name!r}: {e}")
            return False

    def _safe_play_effect(self, name):
        """Play a previously loaded effect; a no-op if it never loaded."""
        if name in self.game.mixer.effects:
            try:
                self.game.mixer.play_effect(name)
            except Exception as e:
                print(f"[WhackAMole] could not play {name!r}: {e}")

    def _safe_load_music(self, name):
        """Start a looping backing track if present; quietly skip if it is missing."""
        try:
            self.game.mixer.load_music(name, loops=-1)
            self.game.mixer.set_music_volume(0.5)
        except Exception as e:
            print(f"[WhackAMole] backing music unavailable: {e}")


# Instantiate once at import so it registers with the StateMachine.
WhackAMole()
