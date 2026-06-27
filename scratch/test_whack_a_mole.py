"""
Headless logic smoke test for the WhackAMole feature.

Drives a real Game with a scripted input register (no display/keyboard needed),
stepping frames and asserting mode selection, spawning, hit scoring, fair
half-balance, and winner resolution. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python scratch/test_whack_a_mole.py
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


def main():
    piso = ScriptedPISO()
    sipo = DummySIPO()
    game = Game(PISOreg=piso, SIPOreg=sipo, mixer=Mixer(), events=events)
    dt = 1000 / config.FPS

    def prog():
        return game.state_machine.program

    def name():
        return prog().__class__.__name__

    def step(word, frames=1):
        piso.word = word
        for _ in range(frames):
            game.update(dt)
            game.render()

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    # --- launch straight into WhackAMole (bypasses the menu) ---
    game.state_machine.launch_single_program("WhackAMole")
    check("launches into WhackAMole", name() == "WhackAMole")
    check("starts in READY (mode select)", prog().phase == "READY")

    # the fixed clips loaded (hammer on every press, mole-hit on a hit, pop-up on spawn)
    fx = game.mixer.effects
    check("hammer clip loaded", prog().hammer in fx)
    check("mole-hit clip loaded", prog().mole_hit in fx)
    check("pop-up clip loaded", prog().popup in fx)

    # --- 1-player: a BLACK button (port 2) starts single mode ---
    step(1 << 2)       # press a black button
    step(0)            # release
    p = prog()
    check("black button -> single mode", p.mode == "single")
    check("single mode -> PLAY", p.phase == "PLAY")
    check("single mode has one half", len(p.sides) == 1)
    check("a mole was primed at play start", len(p.moles) >= 1)
    check("single-mode moles only on left half (0-6)",
          all(port in p.left_ports for port in p.moles))

    # run a while so spawns/expiries cycle; moles must stay on the left half
    step(0, frames=120)
    check("after play, still only left-half moles",
          all(port in p.left_ports for port in p.moles))
    check("left half actually spawned moles", p.spawn_count["left"] > 0)

    # whack a live mole -> score increments, that mole clears
    target = next(iter(p.moles))
    before = p.score["left"]
    step(1 << target)
    check("whacking a mole scores a point", p.score["left"] == before + 1)

    # --- 2-player: a WHITE button (port 10) starts multi mode ---
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    check("relaunch back to READY", p.phase == "READY")
    step(1 << 10)      # press a white button
    step(0)
    check("white button -> multi mode", p.mode == "multi")
    check("multi mode -> PLAY", p.phase == "PLAY")
    check("multi mode has two halves", len(p.sides) == 2)

    # let it run untouched: both halves must stay balanced (the fairness contract)
    step(0, frames=400)
    left_spawns = p.spawn_count["left"]
    right_spawns = p.spawn_count["right"]
    check("both halves spawned moles", left_spawns > 0 and right_spawns > 0)
    check(f"halves stay balanced (L={left_spawns}, R={right_spawns}, diff<=1)",
          abs(left_spawns - right_spawns) <= 1)

    # --- winner resolution (drive scores directly, then ring the buzzer) ---
    def winner_word(p):
        return p._result_word

    # player 1 (left) ahead
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)                      # white -> multi
    p.score = {"left": 5, "right": 3}
    p._congrats_dur = 0.05
    p._end_round()
    check("L>R -> RESULT", p.phase == "RESULT")
    check("L>R -> left half is the winner display",
          winner_word(p) == p._word(p.left_ports))

    # player 2 (right) ahead
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)
    p.score = {"left": 1, "right": 6}
    p._congrats_dur = 0.05
    p._end_round()
    check("R>L -> right half is the winner display",
          winner_word(p) == p._word(p.right_ports))

    # tie -> whole row
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)
    p.score = {"left": 4, "right": 4}
    p._congrats_dur = 0.05
    p._end_round()
    check("tie -> all lasers lit", winner_word(p) == p.ALL_WORD)

    # --- a press on an empty hole is harmless (no score, no crash) ---
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 2); step(0)                      # black -> single
    p.moles = {}                               # clear the board
    empty_port = 6
    step(1 << empty_port)
    check("empty-hole press does not score", p.score["left"] == 0)

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
