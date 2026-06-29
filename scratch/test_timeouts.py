"""Integration tests: in-game timeouts measure real time, not frame counts.

Drives real programs (GameSelect, Trivia) through the real ``Game`` and asserts
the invariant the boot-timing bug broke:

* a timeout window lasts its configured number of **milliseconds of game time**;
* that duration is **independent of frame rate** (same wall-time at 100fps as at
  2fps -- it is not a count of frames);
* it is **immune to a wall-clock leap** -- the exact failure mode on the box,
  where ``systemd-timesyncd`` stepped ``time.time()`` forward mid-session and
  used to compress every window to a fraction of a second. Here we drive the real
  ``GameClock`` off a fake monotonic clock while corrupting ``time.time()``, and
  show the arm window still lasts its full ~10 s.

Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_timeouts.py
"""
import os
import sys
import time as real_time

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = [sys.argv[0], "-s"]

from src import clock
from src.game_loop import Game, GameClock
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


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t
    def monotonic(self):
        return self.t
    def sleep(self, secs):
        if secs > 0:
            self.t += secs


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label)


def new_game():
    game = Game(PISOreg=ScriptedPISO(), SIPOreg=DummySIPO(),
                mixer=Mixer(), events=events)
    return game


def advance(game, ms, dt):
    """Advance ``ms`` of game time in steps of ``dt`` (no input), one frame each."""
    elapsed = 0.0
    while elapsed < ms:
        game.update(dt)
        elapsed += dt


# === GameSelect arm window: measured in ms, independent of frame size ========
def test_arm_window_measures_milliseconds():
    window = config.GameSelect.ARM_TIMEOUT_MS
    for dt in (1000.0 / config.FPS, 500.0, 5.0):
        game = new_game()
        gs = game.state_machine.program
        # First press of slot 0 arms it (does not launch).
        game.input_manager.register.word = 1 << 0
        game.update(dt)
        game.input_manager.register.word = 0          # release; arm persists
        armed_ok = gs.armed == 0
        # Just shy of the window: still armed.
        advance(game, window - 3 * dt, dt)
        still_armed = gs.armed == 0
        # Cross the window: it disarms.
        advance(game, 6 * dt, dt)
        expired = gs.armed is None
        check(f"arm window holds then expires at ~{window}ms (dt={dt:g}ms)",
              armed_ok and still_armed and expired)


def test_arm_window_is_not_a_frame_count():
    """Same window, two very different frame rates => same wall-time to expiry."""
    window = config.GameSelect.ARM_TIMEOUT_MS
    frames_to_expire = {}
    for dt in (10.0, 250.0):   # 100fps vs 4fps
        game = new_game()
        gs = game.state_machine.program
        game.input_manager.register.word = 1 << 0
        game.update(dt)
        game.input_manager.register.word = 0
        frames = 1
        while gs.armed is not None and frames < 100000:
            game.update(dt)
            frames += 1
        frames_to_expire[dt] = frames
    fast_ms = frames_to_expire[10.0] * 10.0
    slow_ms = frames_to_expire[250.0] * 250.0
    check("100fps run expires in ~window ms", abs(fast_ms - window) <= 2 * 10.0)
    check("4fps run expires in ~window ms", abs(slow_ms - window) <= 2 * 250.0)
    check("expiry is a duration, not a frame count "
          f"(fast={frames_to_expire[10.0]} frames vs slow={frames_to_expire[250.0]})",
          frames_to_expire[10.0] > 10 * frames_to_expire[250.0])


# === The original bug: a wall-clock leap must not compress the window ========
def test_arm_window_survives_wall_clock_leap():
    fake = FakeClock()
    restore = clock.set_source(fake.monotonic, fake.sleep)
    saved_time = real_time.time
    try:
        game = new_game()
        gc = GameClock(config.FPS)
        game.clock = gc
        gs = game.state_machine.program

        dt = 1000.0 / config.FPS
        # Frame 0: arm slot 0.
        game.input_manager.register.word = 1 << 0
        game.update(dt)
        dt = gc.tick()
        game.input_manager.register.word = 0

        armed_at_start = gs.armed == 0
        leaped = False
        disarm_ms = None
        start_now = game.now_ms
        for f in range(2000):
            game.update(dt)
            # Mid-session, systemd-timesyncd steps the WALL clock forward 15 min.
            if f == 50 and not leaped:
                real_time.time = lambda: 9.0e8  # absurd forward jump
                leaped = True
            if gs.armed is None:
                disarm_ms = game.now_ms - start_now
                break
            dt = gc.tick()

        window = config.GameSelect.ARM_TIMEOUT_MS
        check("armed at start", armed_at_start)
        check("did not disarm early despite the wall-clock leap",
              disarm_ms is not None and disarm_ms >= window - 5 * 10.0)
        check(f"disarmed at ~{window}ms of real (monotonic) game time",
              disarm_ms is not None and abs(disarm_ms - window) <= 5 * 10.0)
    finally:
        real_time.time = saved_time
        restore()


# === Trivia buzz window also measured in ms (the user's other example) =======
def _launch_trivia(game, questions):
    class FakeSource:
        def __init__(self, qs):
            self.questions = list(qs); self._i = 0
            self.match_length = len(qs)
        def prepare(self): pass
        def has_next(self): return self._i < len(self.questions)
        def next_question(self):
            q = self.questions[self._i]; self._i += 1; return q

    class SilentVoice:
        def preload(self, qs): pass
        def say_line(self, key, on_done=None): on_done and on_done()
        def say_question(self, q, number=None, on_done=None, with_intro=True, with_choices=False): on_done and on_done()
        def say_choice(self, q, slot, on_done=None): on_done and on_done()
        def choice_length(self, q, slot): return 0.0
        def line_length(self, key): return 0.0
        def say_correct_answer(self, q, on_done=None): on_done and on_done()
        def say_score(self, b, w, on_done=None): on_done and on_done()
        def interrupt(self): pass
        def release(self): pass
        @property
        def busy(self): return False

    trivia_mod.select_source_and_voice = lambda mixer, schedule, rng=None: (
        FakeSource(questions), SilentVoice())
    game.state_machine.launch_single_program("Trivia")
    return game.state_machine.program


def test_trivia_buzz_window_measures_milliseconds():
    q = Question(id="q", category="", difficulty="", question="?",
                 choices=("A", "B", "C", "D"), correct_index=0)
    BLACK_BUZZ, WHITE_BUZZ = config.Trivia.BLACK_BUZZ, config.Trivia.WHITE_BUZZ
    window = config.Trivia.POST_QUESTION_BUZZ_MS

    for dt in (1000.0 / config.FPS, 300.0):
        game = new_game()
        triv = _launch_trivia(game, [q, q])
        # Ready handshake: both teams buzz in. The match then begins after a real
        # after()-scheduled beat (READY_BEAT_MS) -- itself game-time driven -- so
        # pump frames until question 1 opens its buzz window.
        for b in (BLACK_BUZZ, WHITE_BUZZ):
            game.input_manager.register.word = 1 << b
            game.update(dt)
            game.input_manager.register.word = 0
            game.update(dt)
        guard = 0
        while triv.buzz_deadline is None and guard < 100000:
            game.update(dt)
            guard += 1
        opened = triv.buzz_deadline is not None and triv.q_number == 1

        # Nobody buzzes: the post-question window must last ~POST_QUESTION_BUZZ_MS
        # of game time from when it opened (measured against the live deadline).
        remaining = triv.buzz_deadline - game.now_ms
        window_ok = abs(remaining - window) <= 2 * dt
        q1 = triv.q_number
        advance(game, remaining - 4 * dt, dt)
        still_q1 = triv.q_number == q1 and triv.phase is trivia_mod._Phase.ASKING
        advance(game, 8 * dt, dt)
        timed_out = triv.q_number != q1 or triv.phase is not trivia_mod._Phase.ASKING
        check(f"trivia buzz window lasts ~{window}ms then times out (dt={dt:g}ms)",
              opened and window_ok and still_q1 and timed_out)


def main():
    test_arm_window_measures_milliseconds()
    test_arm_window_is_not_a_frame_count()
    test_arm_window_survives_wall_clock_leap()
    test_trivia_buzz_window_measures_milliseconds()

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
