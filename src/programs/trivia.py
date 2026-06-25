"""Trivia: a two-player buzz-in face-off.

**Black team** (left half of the box, keys 0-6) plays **White team** (right half,
keys 7-13). Each team buzzes with its endcap button (Black = 6, White = 7) and
answers on its four choice buttons; the two halves are mirror images, so choice
*slot* ``i`` is Black's ``BLACK_CHOICES[i]`` or White's ``WHITE_CHOICES[i]``.

Flow of one match (``config.Trivia.QUESTIONS_PER_MATCH`` questions, highest score
wins):

* **Ready** -- "both teams buzz to begin"; each buzz lights that endcap. Once both
  are in, the match starts.
* **Asking** -- the question is read aloud; buzzing is live from the first word. A
  buzz **cuts the question audio instantly** (see :class:`..trivia_voice._VoSequencer`)
  and hands that team the answer.
* **Answering** -- the buzzing team's four choice buttons go live. Pressing one
  speaks + arms that choice; pressing it **again** locks it in; a different button
  re-arms. A lock-in timeout counts as a miss.
* **Resolve** -- correct: cheer + laser dance; wrong: buzzer + flash. A first-buzz
  miss hands a **steal** to the other team (full question re-read) at lower stakes.
* **Score** -- the running score is read aloud after every question.

Scoring (negatives allowed): first buzz +2 / -1; steal +1 / 0. A tie after the
last question goes to sudden death.

Question sourcing and voice-over are pluggable strategies; see
:mod:`~src.programs.trivia_source` and :mod:`~src.programs.trivia_voice`. On the
box the runtime path is the local bank + pre-baked edge-tts audio (the Pi Zero W
can't run a neural TTS).
"""
import os
from enum import Enum, auto

from .base import *
from ..event_loop import events, EventType
from ..config import config
from ..animation import random_k_dance
from .trivia_source import BankSource, SourceUnavailable
from .trivia_voice import select_source_and_voice, PrebakedVoice


class _Phase(Enum):
    """Where a round currently is. Only READY/ASKING/ANSWERING accept input."""
    READY = auto()          # waiting for both teams to buzz in
    ASKING = auto()         # reading the question; buzzing is live
    ANSWERING = auto()      # a team is choosing (arm/confirm)
    RESOLVING = auto()      # playing correct/wrong feedback
    STEAL_READING = auto()  # re-reading the question for the stealing team
    SCORING = auto()        # reading the running score aloud
    DONE = auto()           # match over; winner announced


class Trivia(Program):
    """Two-player buzz-in trivia face-off (Black team vs White team)."""

    # Shared sound effects (paths under assets/sounds/effects).
    BUZZ_IN = os.path.join("positive", "achievement_unlocked.wav")  # a team buzzes
    CORRECT = os.path.join("positive", "hooray.wav")
    WRONG = os.path.join("simon", "buzz.wav")
    CONGRATS = os.path.join("positive", "congrats_extended.wav")    # match-end fanfare

    # Feedback / pacing windows (ms).
    READY_BEAT_MS = 600        # pause after both teams are in, before "let's begin"
    CORRECT_FEEDBACK_MS = 3200  # covers the cheer + celebratory laser dance
    WRONG_FEEDBACK_MS = 1400    # covers the buzzer + miss flash
    END_BEAT_MS = 2800          # let the winner line + dance play before quitting

    def __init__(self):
        super().__init__()

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        """Pick strategies, reset all run state, and open the ready handshake."""
        self.cfg = config.Trivia
        self._setup_mappings()
        self._reset_run_state()
        self._all_off()

        self.source, self.voice = self._make_strategy()
        if self.source is None:
            print("[Trivia] no questions available; returning to menu")
            return self.after(500, self.quit)
        self.match_length = self.source.match_length
        self._enter_ready()

    def teardown(self):
        """Stop any voice-over and release the reserved VO channel, then base."""
        voice = getattr(self, "voice", None)
        if voice is not None:
            voice.interrupt()
            voice.release()
        super().teardown()

    def quit(self):
        """Clear the lasers and hand control back to the state machine."""
        self._all_off()
        super().quit()

    def _setup_mappings(self):
        cfg = self.cfg
        # endcap button -> team, and the reverse
        self.endcap = {"black": cfg.BLACK_BUZZ, "white": cfg.WHITE_BUZZ}
        self.team_of_buzz = {cfg.BLACK_BUZZ: "black", cfg.WHITE_BUZZ: "white"}
        # choice button -> (team, slot), and each team's ordered choice buttons
        self.team_choices = {"black": list(cfg.BLACK_CHOICES),
                             "white": list(cfg.WHITE_CHOICES)}
        self.choice_of_button = {}
        for team, buttons in self.team_choices.items():
            for slot, button in enumerate(buttons):
                self.choice_of_button[button] = (team, slot)

    def _reset_run_state(self):
        self.phase = _Phase.READY
        self.score = {"black": 0, "white": 0}
        self.q_number = 0           # 1-based number of the current question
        self.question = None
        self.current_team = None    # team currently answering
        self.current_stakes = None  # "first" or "steal"
        self.first_team = None      # who buzzed first this question (steal routing)
        self.armed_slot = None      # choice slot armed but not yet locked in
        self.answer_deadline = None
        self.buzz_deadline = None
        self.ready_deadline = None
        self.ready = {"black": False, "white": False}
        self._warned = False    # has the 5-second warning fired for the active window

    def _make_strategy(self):
        """Return a prepared ``(source, voice)``, falling back live -> bank.

        Returns ``(None, None)`` only if even the bank yields no questions.
        """
        source, voice = select_source_and_voice(self.game.mixer, self.after)
        try:
            source.prepare()
            return source, voice
        except SourceUnavailable as e:
            print(f"[Trivia] {type(source).__name__} unavailable ({e}); "
                  "falling back to bank")
        source = BankSource(self.cfg.QUESTIONS_PER_MATCH,
                            playlist=self.cfg.CURATED_PLAYLIST,
                            whitelist=self.cfg.WHITELIST)
        voice = PrebakedVoice(self.game.mixer, self.after)
        try:
            source.prepare()
            return source, voice
        except SourceUnavailable as e:
            print(f"[Trivia] bank unavailable ({e})")
            return None, None

    # -- per-frame update ---------------------------------------------------
    def update(self, dt):
        """Service timers, then dispatch input by phase."""
        super().update(dt)
        self._check_timers()
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self._on_button_down(event.key)

    def _check_timers(self):
        now = self.now_ms
        if self.phase is _Phase.ASKING and self.buzz_deadline is not None:
            self._maybe_warn(self.buzz_deadline)
            if now > self.buzz_deadline:
                self._no_buzz_timeout()
        elif self.phase is _Phase.ANSWERING and self.answer_deadline is not None:
            self._maybe_warn(self.answer_deadline)
            if now > self.answer_deadline:
                self._answer_timeout()
        elif self.phase is _Phase.READY:
            if self.ready_deadline is not None and now > self.ready_deadline:
                self._reprompt_ready()

    def _maybe_warn(self, deadline):
        """Announce 'five seconds remaining' once, WARNING_MS before a deadline."""
        if self._warned:
            return
        if self.now_ms >= deadline - self.cfg.WARNING_MS:
            self._warned = True
            self.voice.say_line("five_seconds_remaining")

    def _on_button_down(self, button):
        if self.phase is _Phase.READY:
            self._ready_buzz(button)
        elif self.phase is _Phase.ASKING:
            self._asking_buzz(button)
        elif self.phase is _Phase.ANSWERING:
            self._answering_press(button)
        # RESOLVING / STEAL_READING / SCORING / DONE: input is inert

    # -- ready handshake ----------------------------------------------------
    def _enter_ready(self):
        self.phase = _Phase.READY
        self.ready = {"black": False, "white": False}
        self._all_off()
        self.ready_deadline = self.now_ms + self.cfg.READY_REPROMPT_MS
        self.voice.say_line("ready_prompt")

    def _reprompt_ready(self):
        """A team stalled at the ready screen -- nudge with the prompt again."""
        self.ready_deadline = self.now_ms + self.cfg.READY_REPROMPT_MS
        self.voice.say_line("ready_prompt")

    def _ready_buzz(self, button):
        team = self.team_of_buzz.get(button)
        if team is None or self.ready[team]:
            return
        self.ready[team] = True
        self.game.lasers.turn_on(self.endcap[team])
        self.game.mixer.play_effect(self.BUZZ_IN)
        if all(self.ready.values()):
            self.ready_deadline = None
            self.after(self.READY_BEAT_MS, self._begin_match)

    def _begin_match(self):
        self._all_off()
        self.voice.say_line("lets_begin", on_done=self._next_question)

    # -- question flow ------------------------------------------------------
    def _next_question(self):
        question = self.source.next_question()
        if question is None:
            return self._end_match()  # ran out (e.g. endless sudden-death tie)
        self.question = question
        self.q_number += 1
        self._start_asking()

    def _start_asking(self):
        self.phase = _Phase.ASKING
        self.buzz_deadline = None
        self.first_team = None
        self.armed_slot = None
        self._all_off()
        self.voice.say_question(self.question, self._ordinal(),
                                on_done=self._question_fully_read)

    def _question_fully_read(self):
        """Question read out with no buzz -> open a short post-question window."""
        if self.phase is _Phase.ASKING:
            self.buzz_deadline = self.now_ms + self.cfg.POST_QUESTION_BUZZ_MS
            self._warned = False

    def _asking_buzz(self, button):
        team = self.team_of_buzz.get(button)
        if team is None:
            return  # only the endcaps buzz; choice buttons do nothing yet
        self.voice.interrupt()              # cut the question audio instantly
        self.buzz_deadline = None
        self.first_team = team
        self._all_off()
        self.game.lasers.turn_on(self.endcap[team])
        self.game.mixer.play_effect(self.BUZZ_IN)
        self.voice.say_line(f"{team}_team")  # confirm aloud who buzzed in first
        self._begin_answer(team, "first")

    def _no_buzz_timeout(self):
        """Nobody buzzed: reveal the answer, no score, then announce + advance."""
        self.phase = _Phase.RESOLVING
        self.buzz_deadline = None
        self._all_off()
        self.voice.say_correct_answer(self.question, on_done=self._score_announce)

    # -- answering (arm / confirm) -----------------------------------------
    def _begin_answer(self, team, stakes):
        self.phase = _Phase.ANSWERING
        self.current_team = team
        self.current_stakes = stakes
        self.armed_slot = None
        self.answer_deadline = self.now_ms + self.cfg.ANSWER_TIMEOUT_MS
        self._warned = False

    def _answering_press(self, button):
        mapping = self.choice_of_button.get(button)
        if mapping is None:
            return
        team, slot = mapping
        if team != self.current_team:
            return  # the other team's buttons are inert during this turn
        self.answer_deadline = self.now_ms + self.cfg.ANSWER_TIMEOUT_MS
        self._warned = False               # activity resets the countdown + warning
        if slot == self.armed_slot:
            self._lock_in(slot)            # second press of the armed choice
        else:
            self._arm_choice(team, slot)   # arm (or re-arm to) this choice

    def _arm_choice(self, team, slot):
        # clear every laser first so the *other* team's laser is always off once
        # this team's choice lights (covers the steal hand-off), then light it.
        self._all_off()
        self.game.lasers.turn_on(self.team_choices[team][slot])
        self.armed_slot = slot
        self.voice.say_choice(self.question, slot)

    def _lock_in(self, slot):
        self.answer_deadline = None
        self._resolve(slot == self.question.correct_index)

    def _answer_timeout(self):
        """Deadline hit: auto-pick an armed-but-unconfirmed choice, else a miss."""
        self.answer_deadline = None
        self.voice.interrupt()
        if self.armed_slot is not None:
            self._lock_in(self.armed_slot)   # an armed choice becomes their final answer
        else:
            self._resolve(False)             # nothing armed -> a miss

    # -- resolution / steal -------------------------------------------------
    def _resolve(self, correct):
        self.phase = _Phase.RESOLVING
        team, stakes = self.current_team, self.current_stakes
        if correct:
            self.score[team] += (self.cfg.SCORE_FIRST_RIGHT if stakes == "first"
                                 else self.cfg.SCORE_STEAL_RIGHT)
            self._feedback_correct()
            self.after(self.CORRECT_FEEDBACK_MS, self._score_announce)
        else:
            self.score[team] += (self.cfg.SCORE_FIRST_WRONG if stakes == "first"
                                 else self.cfg.SCORE_STEAL_WRONG)
            self._feedback_wrong(team)
            if stakes == "first":
                self.after(self.WRONG_FEEDBACK_MS, self._begin_steal)
            else:
                self.after(self.WRONG_FEEDBACK_MS, self._reveal_then_score)

    def _begin_steal(self):
        """Hand the unanswered question to the other team (lower stakes)."""
        other = "white" if self.first_team == "black" else "black"
        self.phase = _Phase.STEAL_READING
        self.current_team = other
        self.armed_slot = None
        self._all_off()
        self.game.lasers.turn_on(self.endcap[other])   # "your turn" cue
        self.game.mixer.play_effect(self.BUZZ_IN)
        # steal cue, then re-read the FULL question so the early interruption
        # never disadvantages the stealing team, then open their answer.
        self.voice.say_line(f"steal_{other}", on_done=self._reread_for_steal)

    def _reread_for_steal(self):
        self.voice.say_question(self.question, self._ordinal(), with_intro=False,
                                on_done=lambda: self._begin_answer(self.current_team,
                                                                   "steal"))

    def _reveal_then_score(self):
        self.voice.say_correct_answer(self.question, on_done=self._score_announce)

    # -- scoring / end ------------------------------------------------------
    def _score_announce(self):
        self.phase = _Phase.SCORING
        self._all_off()
        self.voice.say_score(self.score["black"], self.score["white"],
                             on_done=self._advance_after_score)

    def _advance_after_score(self):
        if self.q_number < self.match_length:
            return self._next_question()
        if self.score["black"] != self.score["white"]:
            return self._end_match()
        self._next_question()  # tied after regulation -> sudden death

    def _end_match(self):
        self.phase = _Phase.DONE
        self._all_off()
        black, white = self.score["black"], self.score["white"]
        if black > white:
            key = "black_wins"
        elif white > black:
            key = "white_wins"
        else:
            key = "tie"
        if key != "tie":
            self.game.mixer.play_effect(self.CONGRATS)   # fanfare under the dance
            random_k_dance(k=3, fps=8, dur=2.5).start()
        self.voice.say_line(key, on_done=lambda: self.after(self.END_BEAT_MS, self.quit))

    # -- feedback -----------------------------------------------------------
    def _feedback_correct(self):
        self.game.mixer.play_effect(self.CORRECT)
        random_k_dance(k=3, fps=8, dur=2.5).start()

    def _feedback_wrong(self, team):
        self.game.mixer.play_effect(self.WRONG)
        self._flash_team(team)

    def _flash_team(self, team, times=3, period_ms=140):
        """Blink the team's four choice lasers (the miss flash)."""
        buttons = self.team_choices[team]
        for n in range(times):
            self.after(n * period_ms, self._set_lasers, buttons, True)
            self.after(n * period_ms + period_ms // 2, self._set_lasers, buttons, False)

    def _set_lasers(self, buttons, on):
        for button in buttons:
            self.game.lasers.set_value(button, 1 if on else 0)

    # -- helpers ------------------------------------------------------------
    def _all_off(self):
        """Clear every laser via per-port writes. Plain ``set_word(0)`` leaves
        LaserBay's per-port state stale, so a later ``turn_on`` recomputes the
        word from ports and can re-light a laser that was 'cleared' (e.g. the
        first team's endcap lingering into a steal when they never armed a
        choice). Per-port turn_off keeps word and ports consistent."""
        for laser_id in range(14):
            self.game.lasers.turn_off(laser_id)

    def _ordinal(self):
        """Ordinal token for the question intro clip ("sudden" past regulation)."""
        return self.q_number if self.q_number <= self.match_length else "sudden"


# Instantiate once at import so it registers with the StateMachine.
Trivia()
