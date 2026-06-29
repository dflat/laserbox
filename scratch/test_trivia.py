"""Headless logic smoke test for Trivia.

Drives a real Game with a scripted input register (no display/keyboard) and
injects a deterministic FakeSource + SilentVoice in place of the live
source/voice selection. Voice-over is silent and ``after`` is made synchronous so
phase transitions resolve immediately -- this tests the game *logic* (ready
handshake, buzz cuts the question, arm/confirm, scoring, steal, no-buzz timeout,
answer timeout, win, sudden-death), not real-time pacing or audio (best eyeballed
in the simulator). Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_trivia.py
"""
import os
import sys

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = [sys.argv[0], "-s"]  # '-s' => simulator (skip RPi.GPIO, no network)

from src.game_loop import Game
from src.audio_utils import Mixer
from src.event_loop import events
from src.config import config
from src.programs import trivia as trivia_mod
from src.programs.trivia_source import Question


class ScriptedPISO:
    def __init__(self):
        self.word = 0
    def read_word(self):
        return self.word


class DummySIPO:
    def __init__(self):
        self.last = 0
    def push_word(self, word):
        self.last = word


class FakeSource:
    """Hands out a fixed question list; match_length controls regulation length."""
    def __init__(self, questions, match_length=None):
        self.questions = list(questions)
        self.match_length = len(questions) if match_length is None else match_length
        self._i = 0
    def prepare(self):
        pass
    def next_question(self):
        if self._i < len(self.questions):
            q = self.questions[self._i]
            self._i += 1
            return q
        return None
    def has_next(self):
        return self._i < len(self.questions)


class RecordingSilentVoice:
    """SilentVoice-alike: plays nothing, fires on_done now, counts interrupts."""
    def __init__(self):
        self.interrupts = 0
        self.lines = []
        self.questions = []   # (question_id, with_intro, with_choices) per read-out
    def _done(self, on_done):
        if on_done:
            on_done()
    def preload(self, questions): pass
    def say_line(self, key, on_done=None): self.lines.append(key); self._done(on_done)
    def say_first_to(self, target, on_done=None): self.lines.append(("first_to", target)); self._done(on_done)
    def say_question(self, q, number=None, on_done=None, with_intro=True, with_choices=False):
        self.questions.append((q.id, with_intro, with_choices)); self._done(on_done)
    def say_choice(self, q, slot, on_done=None): self._done(on_done)
    def choice_length(self, q, slot): return 0.0
    def line_length(self, key): return 0.0
    def say_correct_answer(self, q, on_done=None): self._done(on_done)
    def say_score(self, b, w, on_done=None): self._done(on_done)
    def interrupt(self): self.interrupts += 1
    def release(self): pass
    @property
    def busy(self): return False


def Q(qid, correct_index):
    return Question(id=qid, category="", difficulty="",
                    question=f"Question {qid}?",
                    choices=("A", "B", "C", "D"), correct_index=correct_index)


# Button ids per the symmetric layout in config.Trivia.
BLACK_BUZZ, WHITE_BUZZ = config.Trivia.BLACK_BUZZ, config.Trivia.WHITE_BUZZ
BLACK = config.Trivia.BLACK_CHOICES   # slot -> button
WHITE = config.Trivia.WHITE_CHOICES


def main():
    piso, sipo = ScriptedPISO(), DummySIPO()
    game = Game(PISOreg=piso, SIPOreg=sipo, mixer=Mixer(), events=events)
    dt = 1000 / config.FPS

    def prog():
        return game.state_machine.program

    def name():
        return prog().__class__.__name__

    def step(word):
        piso.word = word
        game.update(dt)
        game.render()

    def press(b):
        step(1 << b)
        step(0)

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    def launch(questions, match_length=None):
        """Patch selection to our fakes, launch Trivia, make after synchronous."""
        voice = RecordingSilentVoice()
        src = FakeSource(questions, match_length)
        trivia_mod.select_source_and_voice = lambda mixer, schedule, rng=None: (src, voice)
        game.state_machine.launch_single_program("Trivia")
        t = prog()
        t.after = lambda ms, fn, *a, **k: fn(*a, **k)  # fire scheduled work now
        return t, voice

    # --- wiring ---------------------------------------------------------
    check("Trivia registered", "Trivia" in game.state_machine.PROGRAMS)
    check("menu slot 6 is Trivia",
          config.GameSelect.MENU.get(6, (None,))[0] == "Trivia")

    # === Scenario A: ready handshake, buzz cut, +2, wrong->steal +1, win ===
    triv, voice = launch([Q("q1", 2), Q("q2", 0), Q("q3", 1)], match_length=3)
    check("A: launched into Trivia", name() == "Trivia")
    check("A: starts in READY", triv.phase is trivia_mod._Phase.READY)

    press(BLACK_BUZZ)
    check("A: black ready after its buzz", triv.ready["black"] is True)
    check("A: white not ready yet", triv.ready["white"] is False)
    check("A: black endcap laser lit", bool(sipo.last & (1 << BLACK_BUZZ)))
    check("A: still READY (one team in)", triv.phase is trivia_mod._Phase.READY)

    press(WHITE_BUZZ)
    check("A: both in -> match begins at question 1", triv.q_number == 1)
    check("A: phase is ASKING", triv.phase is trivia_mod._Phase.ASKING)

    n0 = voice.interrupts
    press(BLACK_BUZZ)  # buzz during the question
    check("A: buzz interrupts the question audio", voice.interrupts == n0 + 1)
    check("A: buzz announces the buzzing team", "black_team" in voice.lines)
    check("A: phase ANSWERING, black owns it", triv.phase is trivia_mod._Phase.ANSWERING
          and triv.current_team == "black" and triv.current_stakes == "first")

    press(BLACK[2])   # arm the correct slot (q1 correct_index == 2)
    check("A: choice armed", triv.armed_slot == 2)
    press(BLACK[2])   # second press locks it in -> correct
    check("A: correct first-buzz scores +2", triv.score["black"] == 2)
    check("A: advanced to question 2", triv.q_number == 2 and triv.phase is trivia_mod._Phase.ASKING)

    # q2 correct_index == 0: white buzzes and misses, black steals correctly
    press(WHITE_BUZZ)
    press(WHITE[1]); press(WHITE[1])   # lock a wrong slot
    check("A: wrong first-buzz scores -1", triv.score["white"] == -1)
    check("A: steal handed to black", triv.phase is trivia_mod._Phase.ANSWERING
          and triv.current_team == "black" and triv.current_stakes == "steal")
    press(BLACK[0]); press(BLACK[0])   # black takes the steal correctly (slot 0)
    check("A: steal correct scores +1", triv.score["black"] == 3)
    check("A: advanced to question 3", triv.q_number == 3)

    # q3 correct_index == 1: black buzzes and wins it -> match ends
    press(BLACK_BUZZ)
    press(BLACK[1]); press(BLACK[1])
    check("A: final score black 5 / white -1", triv.score == {"black": 5, "white": -1})
    check("A: match ended, back at GameSelect", name() == "GameSelect")

    # === Scenario B: a no-buzz question just advances; with no fixed length the
    #     match ends when the question pool is exhausted (no sudden death) ===
    triv, voice = launch([Q("s1", 0), Q("s2", 3)])
    press(BLACK_BUZZ); press(WHITE_BUZZ)   # ready -> question 1
    check("B: at question 1", triv.q_number == 1 and triv.phase is trivia_mod._Phase.ASKING)
    triv.buzz_deadline = triv.now_ms - 1     # force the no-buzz window to expire
    step(0)
    check("B: a no-buzz question simply advances to the next",
          triv.q_number == 2 and triv.phase is trivia_mod._Phase.ASKING)
    check("B: scores unchanged after the no-buzz question", triv.score == {"black": 0, "white": 0})
    press(BLACK_BUZZ)
    press(BLACK[3]); press(BLACK[3])       # s2 correct_index == 3
    check("B: last answer scores, exhausted pool ends the match (higher score wins)",
          triv.score == {"black": 2, "white": 0})
    check("B: match ended, back at GameSelect", name() == "GameSelect")

    # === Scenario C: answer (lock-in) timeout counts as a miss ===
    triv, voice = launch([Q("c1", 0)], match_length=1)
    press(BLACK_BUZZ); press(WHITE_BUZZ)
    press(WHITE_BUZZ)                      # white buzzes first
    check("C: white answering", triv.current_team == "white")
    triv.answer_deadline = triv.now_ms - 1  # force the lock-in deadline to expire
    n0 = voice.interrupts
    step(0)
    check("C: answer timeout interrupts VO", voice.interrupts == n0 + 1)
    check("C: timeout = a miss (-1) and steal handed to black",
          triv.score["white"] == -1 and triv.current_team == "black"
          and triv.current_stakes == "steal")

    # === Scenario D: an armed-but-unconfirmed choice is auto-picked on timeout ===
    triv, voice = launch([Q("d1", 2)], match_length=1)
    press(BLACK_BUZZ); press(WHITE_BUZZ)
    press(BLACK_BUZZ)                       # black buzzes
    press(BLACK[2])                         # ARM the correct slot (2), do NOT confirm
    check("D: choice armed, not locked", triv.armed_slot == 2
          and triv.phase is trivia_mod._Phase.ANSWERING)
    triv.answer_deadline = triv.now_ms - 1    # force the lock-in deadline to expire
    step(0)
    check("D: timeout auto-locks the armed (correct) choice -> +2",
          triv.score["black"] == 2)
    check("D: match ended, back at GameSelect", name() == "GameSelect")

    # === Scenario E: steal laser hygiene when the first team times out unanswered ===
    # Regression: the first team's endcap must not linger once the steal lights up
    # (it never armed a choice, so only set_word(0) used to "clear" it -- which
    # left LaserBay's port state stale and re-lit it).
    triv, voice = launch([Q("e1", 0)], match_length=1)
    press(BLACK_BUZZ); press(WHITE_BUZZ)
    press(BLACK_BUZZ)                          # black buzzes, then never arms a choice
    triv.answer_deadline = triv.now_ms - 1       # time out with NO choice armed
    step(0)
    check("E: steal handed to white", triv.current_team == "white"
          and triv.current_stakes == "steal")
    check("E: black endcap cleared once white's turn lights",
          not (sipo.last & (1 << BLACK_BUZZ)))
    check("E: white endcap lit for the steal", bool(sipo.last & (1 << WHITE_BUZZ)))
    press(WHITE[0])                            # white arms a choice
    check("E: arming leaves only the chosen laser lit", sipo.last == (1 << WHITE[0]))

    # === Scenario F: initial read-out includes choices; steal re-read doesn't ===
    triv, voice = launch([Q("f1", 0)], match_length=1)
    press(BLACK_BUZZ); press(WHITE_BUZZ)       # -> ASKING q1
    check("F: initial question read-out includes the choices (with intro)",
          voice.questions[-1] == ("f1", True, True))
    press(BLACK_BUZZ)                          # black buzzes in first
    press(BLACK[1]); press(BLACK[1])           # locks a wrong slot -> miss -> steal
    check("F: black missed (-1) and white now steals",
          triv.score["black"] == -1 and triv.current_team == "white"
          and triv.current_stakes == "steal")
    check("F: steal re-read is the question only (no choices, no intro)",
          voice.questions[-1] == ("f1", False, False))

    # === Scenario G: the answer deadline is fixed, not reset by selecting ===
    triv, voice = launch([Q("g1", 2)], match_length=1)   # correct slot 2
    press(BLACK_BUZZ); press(WHITE_BUZZ)
    press(BLACK_BUZZ)                          # black answering; deadline set once
    d0 = triv.answer_deadline
    press(BLACK[0])                            # arm a wrong slot
    check("G: deadline not reset by arming a choice", triv.answer_deadline == d0)
    press(BLACK[1])                            # re-arm a different wrong slot
    check("G: deadline still not reset by re-arming", triv.answer_deadline == d0)

    # === Scenario H: the thinking song is the answer clock (warning removed) ===
    # Force the no-asset path (so this is deterministic whether or not a song
    # file is present): the answer window then falls back to ANSWER_TIMEOUT_MS,
    # and the old "five seconds remaining" warning is gone for good.
    triv, voice = launch([Q("h1", 2)], match_length=1)
    triv.thinking_song = None      # force the missing-asset fallback
    triv._song_len_ms = None
    press(BLACK_BUZZ); press(WHITE_BUZZ)       # -> ASKING
    t0 = triv.now_ms
    press(BLACK_BUZZ)                          # black answering; window opens here
    check("H: answer window falls back to ANSWER_TIMEOUT_MS without a song asset",
          triv.answer_deadline is not None
          and abs((triv.answer_deadline - t0) - config.Trivia.ANSWER_TIMEOUT_MS) <= 2 * dt)
    check("H: the five-second warning is gone for good",
          "five_seconds_remaining" not in voice.lines)

    # === Scenario I: the match ends the instant a team reaches TARGET_SCORE ===
    target = config.Trivia.TARGET_SCORE
    per_correct = config.Trivia.SCORE_FIRST_RIGHT
    n_correct = -(-target // per_correct)        # ceil: correct first-buzzes to win
    triv, voice = launch([Q(f"i{i}", 2) for i in range(n_correct + 2)])  # more than enough
    press(BLACK_BUZZ); press(WHITE_BUZZ)   # both ready -> opening announcement + q1
    check("I: opening announces the win condition ('first team to N')",
          ("first_to", target) in voice.lines)
    for _ in range(n_correct - 1):
        press(BLACK_BUZZ); press(BLACK[2]); press(BLACK[2])   # correct: climb toward target
        check("I: still playing while below the target",
              name() == "Trivia" and triv.score["black"] < target)
    press(BLACK_BUZZ); press(BLACK[2]); press(BLACK[2])       # the winning answer
    check("I: reaching TARGET_SCORE wins immediately", triv.score["black"] >= target)
    check("I: no extra question asked after the win (count == answers given)",
          triv.q_number == n_correct)
    check("I: match ended, back at GameSelect", name() == "GameSelect")

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
