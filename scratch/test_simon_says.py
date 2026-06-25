"""Headless logic smoke test for SimonSays.

Drives a real Game with a scripted input register (no display/keyboard). The
demo timing normally runs on wall-clock ``after()`` callbacks; here we override
``after`` to fire callbacks *synchronously* so the round transitions are
deterministic and fast. This tests the game logic (grow on success, lose a life
on a miss, restart on game-over, win at WIN_LENGTH) -- not the real-time pacing,
which is trivial and best eyeballed in the simulator. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_simon_says.py
"""
import os
import sys

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = [sys.argv[0], "-s"]  # '-s' => skip RPi.GPIO import

from src.game_loop import Game
from src.audio_utils import Mixer
from src.event_loop import events
from src.config import config


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


def main():
    piso = ScriptedPISO()
    sipo = DummySIPO()
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
        """Tap button b (down then up) over two frames."""
        step(1 << b)
        step(0)

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    # --- wiring ---------------------------------------------------------
    check("SimonSays registered", "SimonSays" in game.state_machine.PROGRAMS)
    check("menu slot 5 is SimonSays",
          config.GameSelect.MENU.get(5, (None,))[0] == "SimonSays")

    # Launch the game directly (as the -p flag / menu would).
    game.state_machine.launch_single_program("SimonSays")
    check("launched into SimonSays", name() == "SimonSays")
    check("awaiting start", prog().awaiting_start is True)
    check("starts with full lives", prog().lives == config.SimonSays.LIVES)

    # Make demo callbacks fire synchronously so input opens immediately.
    prog().after = lambda ms, fn, *a, **k: fn(*a, **k)

    # --- happy path: play perfectly all the way to a win ----------------
    press(0)  # any play button begins the game
    check("first press leaves awaiting_start", prog().awaiting_start is False)
    check("round 1 opened for input", prog().accepting_input is True)
    check("seed pattern length 1", len(prog().pattern) == 1)

    max_len = 0
    for _ in range(config.SimonSays.WIN_LENGTH + 2):
        if name() != "SimonSays":
            break
        pattern = list(prog().pattern)         # peek to play it back perfectly
        max_len = max(max_len, len(pattern))
        for s in pattern:
            press(s)

    check("pattern grew to WIN_LENGTH", max_len == config.SimonSays.WIN_LENGTH)
    check("winning quits back to GameSelect", name() == "GameSelect")

    # --- regression: the LAST correct press still lights its laser ------
    game.state_machine.launch_single_program("SimonSays")
    prog().after = lambda ms, fn, *a, **k: fn(*a, **k)
    press(0)                                       # begin -> round 1 open
    prog().after = lambda ms, fn, *a, **k: None    # freeze: no instant grow/clear
    last = prog().pattern[-1]
    step(1 << last)                                # final correct press, held down
    check("round cleared by last press", prog().accepting_input is False)
    check("last correct press leaves its laser lit",
          bool(sipo.last & (1 << last)))

    # --- mistake costs a life and replays the SAME round ----------------
    step(0)  # release the held button so the next round's begin press is a clean
             # down-edge even when its seeded step happens to be button 0
    game.state_machine.launch_single_program("SimonSays")
    prog().after = lambda ms, fn, *a, **k: fn(*a, **k)
    press(0)                                   # begin
    first = prog().pattern[0]
    wrong = next(b for b in config.SimonSays.PLAY_BUTTONS if b != first)
    len_before = len(prog().pattern)
    press(wrong)
    check("wrong press loses a life", prog().lives == config.SimonSays.LIVES - 1)
    check("same round replayed (length unchanged)",
          len(prog().pattern) == len_before)
    check("input reopened after miss", prog().accepting_input is True)

    # --- running out of lives refills and restarts from length 1 --------
    remaining = prog().lives                   # misses left before game over
    for _ in range(remaining):
        bad = next(b for b in config.SimonSays.PLAY_BUTTONS
                   if b != prog().pattern[0])
        press(bad)
    check("game over refills lives", prog().lives == config.SimonSays.LIVES)
    check("game over restarts at length 1", len(prog().pattern) == 1)

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
