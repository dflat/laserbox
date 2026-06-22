"""Headless regression test for Flipper state leaking across re-entries.

Reproduces the bug where winning (or partially playing) Flipper corrupted the
shared ``config.Flipper.START_BOARD`` list in place, so re-entering the game
restored the last board -- and, after a win, instantly re-triggered the
"all lasers on" win condition.

Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_flipper_reentry.py
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
        self.last = None
    def push_word(self, word):
        self.last = word


TOGGLE0 = 1 << 14
START_WORD = 0b010101   # config.Flipper.START_BOARD = (1,0,1,0,1,0) -> lasers 0,2,4
ALL_ON = 0b111111       # win: all six lasers on


def main():
    piso = ScriptedPISO()
    sipo = DummySIPO()
    game = Game(PISOreg=piso, SIPOreg=sipo, mixer=Mixer(), events=events)
    dt = 1000 / config.FPS

    original_start_board = tuple(config.Flipper.START_BOARD)

    def prog():
        return game.state_machine.program.__class__.__name__

    def board_word():
        return game.lasers.to_word() & 0b111111

    def step(word):
        piso.word = word
        game.update(dt)
        game.render()

    def launch_flipper():
        # button 1 == Flipper in config.GameSelect.MENU: press to arm, press to launch
        step(0); step(1 << 1); step(0); step(1 << 1)

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    # boots into GameSelect
    check("boots into GameSelect", prog() == "GameSelect")

    # --- first entry: board is the configured start pattern, not a win ---
    launch_flipper()
    check("launched Flipper", prog() == "Flipper")
    check("initial board == START_BOARD pattern", board_word() == START_WORD)
    check("not won on entry", game.state_machine.program.won is False)

    # --- play to a win: pressing buttons 2,3,4 turns all six lasers on ---
    for b in (2, 3, 4):
        step(1 << b); step(0)
    check("reached win (all lasers on)", board_word() == ALL_ON)
    check("win detected", game.state_machine.program.won is True)

    # core invariant: playing must NOT have mutated the shared config list
    check("config.Flipper.START_BOARD unmutated",
          tuple(config.Flipper.START_BOARD) == original_start_board)

    # --- exit via the GameSelect entry gesture (hold btns 0&1, toggle0 x2) ---
    step(0b11)
    step(0b11 | TOGGLE0)
    step(0b11)
    check("gesture exit -> GameSelect", prog() == "GameSelect")

    # --- re-enter Flipper: must be a fresh start, NOT the won board ---
    launch_flipper()
    check("re-launched Flipper", prog() == "Flipper")
    check("re-entry board reset to START_BOARD", board_word() == START_WORD)
    check("re-entry not an instant win", board_word() != ALL_ON)
    check("re-entry won flag is False", game.state_machine.program.won is False)

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
