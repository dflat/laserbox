"""Headless regression test for Flipper's random deal and clean re-entries.

Covers two things:

* The board is dealt fresh and **random** on every entry (between 1 and 5 lasers
  lit -- never empty, never the all-on board that would be an instant win),
  rather than the old fixed start pattern that made every entry identical.
* Winning (or partially playing) Flipper must not leak into the next entry: a
  re-entry is always a fresh deal, never the previous won/all-on board.

Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_flipper_reentry.py
"""
import os
import random
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
ALL_ON = 0b111111       # win: all six lasers on


def main():
    # Seed for a deterministic, reproducible sequence of random deals.
    random.seed(20240625)

    piso = ScriptedPISO()
    sipo = DummySIPO()
    game = Game(PISOreg=piso, SIPOreg=sipo, mixer=Mixer(), events=events)
    dt = 1000 / config.FPS

    def prog():
        return game.state_machine.program.__class__.__name__

    def flipper():
        return game.state_machine.program

    def board_word():
        return game.lasers.to_word() & 0b111111

    def on_count(word):
        return bin(word).count("1")

    def step(word):
        piso.word = word
        game.update(dt)
        game.render()

    def launch_flipper():
        # button 1 == Flipper in config.GameSelect.MENU: press to arm, press to launch
        step(0); step(1 << 1); step(0); step(1 << 1)

    def exit_to_menu():
        # global GameSelect entry gesture: hold buttons 0&1, toggle0 off->on->off
        step(0b11)
        step(0b11 | TOGGLE0)
        step(0b11)

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    # boots into GameSelect
    check("boots into GameSelect", prog() == "GameSelect")

    lo, hi = config.Flipper.MIN_START_ON, config.Flipper.MAX_START_ON

    # --- first entry: a fresh random board, valid and not already won ---
    launch_flipper()
    check("launched Flipper", prog() == "Flipper")
    check(f"entry board has {lo}..{hi} lasers lit", lo <= on_count(board_word()) <= hi)
    check("entry board is not an instant win", board_word() != ALL_ON)
    check("not won on entry", flipper().won is False)

    # --- the deal is randomised across entries (not a fixed pattern) ---
    seen = {board_word()}
    within_bounds = True
    for _ in range(15):
        exit_to_menu()
        check("gesture exit -> GameSelect", prog() == "GameSelect")
        launch_flipper()
        w = board_word()
        seen.add(w)
        within_bounds = within_bounds and (lo <= on_count(w) <= hi)
    check(f"every entry stays within {lo}..{hi} lit", within_bounds)
    check("the deal varies across entries (randomised)", len(seen) > 1)
    check("no entry is ever the all-on instant win", ALL_ON not in seen)

    # --- a win must not carry over into the next entry ---
    p = flipper()
    p.board = [1] * 6      # force the winning all-on state
    p.update_laser()
    step(0)                # one tick detects the win
    check("win detected when all six are lit", p.won is True)

    exit_to_menu()
    check("gesture exit after a win -> GameSelect", prog() == "GameSelect")
    launch_flipper()
    check("re-launched Flipper", prog() == "Flipper")
    check("re-entry is a fresh deal, not the won board", board_word() != ALL_ON)
    check(f"re-entry board has {lo}..{hi} lasers lit",
          lo <= on_count(board_word()) <= hi)
    check("re-entry won flag is False", flipper().won is False)

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
