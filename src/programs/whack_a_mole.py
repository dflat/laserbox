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
import json
import os
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
    RESULT = "RESULT"   # round over: cleared bay, result voice, k-dance, then quit

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
        self.single_min = cfg.SINGLE_MIN_MOLES
        self.single_max = cfg.SINGLE_MAX_MOLES
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
        self.new_highscore = cfg.NEW_HIGHSCORE
        self.new_record_vo = cfg.NEW_RECORD
        self.you_scored = cfg.YOU_SCORED
        self.player_1_scored = cfg.PLAYER_1_SCORED
        self.player_2_scored = cfg.PLAYER_2_SCORED
        self.num_dir = cfg.NUM_DIR
        self.perfect_game = cfg.PERFECT_GAME
        self.and_word = cfg.AND_WORD
        self.miss_word = cfg.MISS_WORD
        self.misses_word = cfg.MISSES_WORD
        self.congrats = cfg.CONGRATS
        self.fallback_patch = cfg.FALLBACK_PATCH
        self.music = cfg.MUSIC

        # Persistent score tracker: solo personal best + 2-player all-time best.
        self.highscore_path = (cfg.HIGHSCORE_PATH if os.path.isabs(cfg.HIGHSCORE_PATH)
                               else os.path.join(config.PROJECT_ROOT, cfg.HIGHSCORE_PATH))
        self._load_scores()

        # Sound effects, loaded in start() (not __init__) so the Sounds are valid
        # against the current mixer, which other programs may have re-initialised.
        # ``hammer`` fires on every press (the mallet swing), ``mole_hit`` only on a
        # successful whack, ``popup`` on each spawn. The spoken stubs + shared
        # celebration load defensively -- a missing wav is simply skipped at play.
        self._safe_load_effect(self.popup, volume=0.6)
        self._safe_load_effect(self.hammer, volume=0.7)
        self._safe_load_effect(self.mole_hit, volume=0.9)
        for name in (self.welcome, self.result_single, self.p1_wins, self.p2_wins,
                     self.tie, self.new_highscore, self.new_record_vo,
                     self.you_scored, self.player_1_scored, self.player_2_scored,
                     self.perfect_game, self.and_word, self.miss_word,
                     self.misses_word):
            self._safe_load_effect(name)
        # Number bank for the spoken score: ones/teens 0-19 + tens 20..90 + hundreds
        # 100/200, from which any 0-299 is composed (see _number_clips).
        for value in list(range(20)) + [20, 30, 40, 50, 60, 70, 80, 90, 100, 200]:
            self._safe_load_effect(self._num_clip(value))
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
        self.misses = {}                # side name -> moles that timed out unwhacked
        self.spawn_count = {}           # side name -> total moles spawned (for balance)
        self.moles = {}                 # port -> remaining lifetime (ms)
        self._clock_ms = 0.0            # free-running clock for blink/prompt phases
        self._elapsed_ms = 0.0          # time into the current round
        self._spawn_accum = 0.0         # accumulator that triggers spawns
        self._winner = None             # 'left' | 'right' | 'tie' set at RESULT (multi)
        self._broke_record = False      # set in RESULT when a saved record is beaten

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
        """Start the timed round: reset scores, prime the board, schedule the buzzer."""
        self.score = {name: 0 for name, _ in self.sides}
        self.misses = {name: 0 for name, _ in self.sides}
        self.spawn_count = {name: 0 for name, _ in self.sides}
        self.moles = {}
        self._elapsed_ms = 0.0
        self._spawn_accum = 0.0
        self.phase = self.PLAY
        self._safe_load_music(self.music)
        for _ in self.sides:           # prime the board so play starts at once
            self._spawn_tick()         # 1-player fills to a random 1..3; 2-player one/half
        self.after(self.round_ms, self._end_round)

    def _age_moles(self, dt):
        """Count down every mole; one that reaches zero has been missed (despawns)."""
        for port in list(self.moles):
            self.moles[port] -= dt
            if self.moles[port] <= 0:
                del self.moles[port]
                self.misses[self._side_of(port)] += 1   # timed out unwhacked = a miss

    def _spawn(self, dt):
        """Spawn moles on the ramping cadence (faster as the round progresses)."""
        self._spawn_accum += dt
        interval = self._spawn_interval()
        while self._spawn_accum >= interval:
            self._spawn_accum -= interval
            self._spawn_tick()
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

    def _spawn_tick(self):
        """One spawn event: 1-player tops up to a random 1..3, 2-player adds one."""
        if self.mode == "single":
            self._spawn_single()
        else:
            self._try_spawn()

    def _spawn_single(self):
        """(1-player) Top the board up to a freshly rolled target of moles.

        Re-rolling a target in ``SINGLE_MIN_MOLES..SINGLE_MAX_MOLES`` each tick
        (rather than spawning one at a time) makes the number of simultaneous moles
        *vary* between those bounds instead of sitting at one.
        """
        name, ports = self.sides[0]
        target = random.randint(self.single_min, self.single_max)
        while sum(1 for p in ports if p in self.moles) < target:
            if not self._spawn_one(name, ports):
                break  # no free ports left on the half

    def _try_spawn(self):
        """(2-player) Pop one mole on the half with the fewest spawns so far.

        Always feeds the half that is "behind" on spawn count; if that half is full
        (``MAX_PER_SIDE`` moles already up) the spawn is skipped rather than handed
        to the other half, so the running counts stay balanced for fair scoring.
        """
        name, ports = min(self.sides, key=lambda s: self.spawn_count[s[0]])
        occupied = sum(1 for p in ports if p in self.moles)
        if occupied < self.max_per_side:
            self._spawn_one(name, ports)

    def _spawn_one(self, name, ports):
        """Light a mole on a random free port of half ``name``; True if one was placed."""
        free = [p for p in ports if p not in self.moles]
        if not free:
            return False
        port = random.choice(free)
        self.moles[port] = self._current_lifetime_ms()
        self.spawn_count[name] += 1
        self._safe_play_effect(self.popup)
        return True

    def _end_round(self):
        """Buzzer: clear the bay, announce the result (+ any record), dance, then quit."""
        self.phase = self.RESULT
        self.moles = {}
        self.game.lasers.set_word(0)   # clear the laser bay the moment the round ends
        self.game.mixer.fade_music(1500)
        self._broke_record = False
        self._winner = None            # 'left' | 'right' | 'tie' (None in 1-player)

        # ``lines`` are the spoken clips played back-to-back before the jingle:
        # the result, the spoken score readout, then a record fanfare if beaten.
        lines = []
        if self.mode == "single":
            score = self.score["left"]
            lines.append(self.result_single)
            lines.append(self.you_scored); lines += self._number_clips(score)
            lines += self._misses_clips(self.misses["left"])   # score + misses (or "perfect game")
            if self._record_broken("solo_best", score):
                lines.append(self.new_highscore)
        else:
            left, right = self.score["left"], self.score["right"]
            lines.append(self.player_1_scored); lines += self._number_clips(left)
            lines += self._misses_clips(self.misses["left"])
            lines.append(self.player_2_scored); lines += self._number_clips(right)
            lines += self._misses_clips(self.misses["right"])
            if left > right:
                self._winner = "left"; lines.append(self.p1_wins)
            elif right > left:
                self._winner = "right"; lines.append(self.p2_wins)
            else:
                self._winner = "tie"; lines.append(self.tie)
            if self._record_broken("versus_best", max(left, right)):
                lines.append(self.new_record_vo)

        # Speak the lines in order (skipping any unrecorded), then fire the
        # celebration so the jingle never talks over an announcement.
        delay = 0
        for name in lines:
            if name in self.game.mixer.effects:
                self.after(delay, self._safe_play_effect, name)
                delay += int(self.game.mixer.effects[name].get_length() * 1000) + 150
        self.after(delay, self._celebrate)
        self.after(delay + int(self._congrats_dur * 1000) + 400, self.quit)

    def _record_broken(self, key, value):
        """Update + persist saved record ``key`` if ``value`` beats it; return True if so.

        ``key`` is ``solo_best`` (1-player personal best) or ``versus_best`` (the
        highest single-side score in a 2-player round). A score of zero never sets
        a record, so an empty round can't "win" the board.
        """
        if value <= 0 or value <= self.scores.get(key, 0):
            return False
        self.scores[key] = value
        self._broke_record = True
        self._save_scores()
        return True

    def _celebrate(self):
        """Flash a celebratory k-dance (bigger on a new record) under the jingle.

        Used for both modes -- the winner is conveyed by the spoken result line, so
        the dance can own the laser bay in 2-player too.
        """
        k = 4 if self._broke_record else 3
        random_k_dance(k=k, fps=8, dur=max(0.0, self._congrats_dur - 1.2)).start()
        self._safe_play_effect(self.congrats)

    # -- rendering ----------------------------------------------------------
    def _render(self):
        """Drive the lasers for the current phase (RESULT is owned by the k-dance)."""
        if self.phase == self.READY:
            self._render_prompt()
        elif self.phase == self.PLAY:
            self._render_moles()

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

    def _num_clip(self, value):
        """Effect path for the single number word ``value`` (0-19 or a ten 20-90)."""
        return f"{self.num_dir}/{value}.wav"

    def _number_clips(self, n):
        """Clip name(s) voicing the integer ``n`` (clamped to 0-299), Trivia-style.

        Composed from the number bank: a hundreds word (100/200) when present, then
        the 0-99 remainder as a tens word plus (unless a round ten) the ones word,
        e.g. 247 -> ["…/200.wav", "…/40.wav", "…/7.wav"]; 200 -> ["…/200.wav"].
        """
        n = max(0, min(299, int(n)))
        hundreds, rem = divmod(n, 100)
        clips = []
        if hundreds:
            clips.append(self._num_clip(hundreds * 100))  # 100 or 200
        if rem or not hundreds:                            # ...05 -> skip; 0 -> "zero"
            clips += self._tens_ones_clips(rem)
        return clips

    def _tens_ones_clips(self, n):
        """Clip name(s) for ``n`` in 0-99 (one clip under 20, else tens + ones)."""
        if n < 20:
            return [self._num_clip(n)]
        tens, ones = (n // 10) * 10, n % 10
        clips = [self._num_clip(tens)]
        if ones:
            clips.append(self._num_clip(ones))
        return clips

    def _misses_clips(self, m):
        """Clip name(s) for the miss readout: 'perfect game', or 'and' + count + miss(es).

        The leading 'and' joins the readout to the score just spoken before it
        ("...five and three misses"). A perfect game (zero misses) stands alone,
        with no 'and' to dangle off.
        """
        if m == 0:
            return [self.perfect_game]
        word = self.miss_word if m == 1 else self.misses_word
        return [self.and_word] + self._number_clips(m) + [word]

    def _load_scores(self):
        """Read the saved records into ``self.scores``; default to zeros if absent.

        Tolerant of a missing/corrupt file: any read error just starts fresh, so a
        first run (or a wiped board) simply has no records yet.
        """
        self.scores = {"solo_best": 0, "versus_best": 0}
        try:
            with open(self.highscore_path) as f:
                data = json.load(f)
            for key in self.scores:
                self.scores[key] = int(data.get(key, 0))
        except (OSError, ValueError, TypeError):
            pass

    def _save_scores(self):
        """Persist ``self.scores`` to the highscore file (best effort)."""
        try:
            os.makedirs(os.path.dirname(self.highscore_path), exist_ok=True)
            with open(self.highscore_path, "w") as f:
                json.dump(self.scores, f)
        except OSError as e:
            print(f"[WhackAMole] could not save scores: {e}")

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
            self.game.mixer.set_music_volume(0.75)
        except Exception as e:
            print(f"[WhackAMole] backing music unavailable: {e}")


# Instantiate once at import so it registers with the StateMachine.
WhackAMole()
