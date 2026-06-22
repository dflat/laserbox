"""
Headless logic smoke test for the GameSelect feature.

Drives a real Game with a scripted input register (no display/keyboard needed),
stepping frames and asserting program transitions. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_gameselect.py
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


def main():
    piso = ScriptedPISO()
    sipo = DummySIPO()
    game = Game(PISOreg=piso, SIPOreg=sipo, mixer=Mixer(), events=events)
    dt = 1000 / config.FPS

    def prog():
        return game.state_machine.program.__class__.__name__

    def step(word):
        piso.word = word
        game.update(dt)
        game.render()

    passed = []
    def check(label, cond):
        passed.append(cond)
        print(("PASS" if cond else "FAIL"), "-", label)

    # 1. boots into GameSelect
    check("boots into GameSelect", prog() == "GameSelect")

    # 2. first press of button 0 arms it (laser 0 lit), does not launch
    step(1 << 0)
    check("press btn0 -> still GameSelect (armed)", prog() == "GameSelect")
    check("armed button is 0", game.state_machine.program.armed == 0)
    check("laser 0 lit while armed", game.lasers.to_word() == (1 << 0))

    # 3. release, then second press of button 0 launches Golf
    step(0)            # button up (ignored by GameSelect)
    check("after release still GameSelect", prog() == "GameSelect")
    step(1 << 0)       # second press -> launch
    check("second press btn0 -> Golf", prog() == "Golf")

    # 4. entry gesture from inside Golf returns to GameSelect
    step(0b11)             # hold buttons 0 & 1, toggle0 off (baseline)
    check("mid-Golf, gesture baseline -> still Golf", prog() == "Golf")
    step(0b11 | TOGGLE0)   # toggle0 on  (transition 1)
    check("gesture transition 1 -> still Golf", prog() == "Golf")
    step(0b11)             # toggle0 off (transition 2) -> fires
    check("gesture transition 2 -> GameSelect", prog() == "GameSelect")

    # 5. arm a different button each press (re-arm), then launch a Composer
    step(0)
    step(1 << 4)       # press btn4 (BirthdayComposer) -> arm
    check("press btn4 -> armed 4", game.state_machine.program.armed == 4)
    step(0)
    step(1 << 4)       # second press -> launch composer's first program
    check("launch BirthdayComposer -> ClueFinder first", prog() == "ClueFinder")
    check("context is a composer with >1 entry",
          len(game.state_machine.context.program_name_sequence) > 1)

    # 6. natural finish of a context program returns toward the menu/next.
    #    Quit the single-entry case: relaunch Golf, then quit -> GameSelect.
    game.state_machine.enter_game_select()
    step(0); step(1 << 0); step(0); step(1 << 0)
    check("relaunched Golf", prog() == "Golf")
    game.state_machine.program.quit()   # natural finish of a one-item context
    check("single-program finish -> GameSelect", prog() == "GameSelect")

    # 7. unassigned button is a no-op
    step(0)
    step(1 << 13)      # button 13 unassigned
    check("unassigned button -> no arm", game.state_machine.program.armed is None)
    check("unassigned button -> still GameSelect", prog() == "GameSelect")

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
