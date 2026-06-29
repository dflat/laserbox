"""
Headless logic smoke test for the GameSelect feature.

Drives a real Game with a scripted input register (no display/keyboard needed),
stepping frames and asserting program transitions. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_gameselect.py
"""
import os
import sys
import tempfile

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
    # Point the per-box volume state at a throwaway temp file so the test never
    # reads or clobbers the real state/system.json (and starts from DEFAULT).
    config.Volume.STATE_PATH = os.path.join(tempfile.mkdtemp(), "system.json")
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

    # 7. unassigned button is a no-op (button 9 is unassigned; 10/11 are volume)
    step(0)
    step(1 << 9)
    check("unassigned button -> no arm", game.state_machine.program.armed is None)
    check("unassigned button -> still GameSelect", prog() == "GameSelect")

    # 8. system slot (btn12 reboot): a different button cancels the pending
    #    action; if that button is itself a menu slot it re-arms to it.
    ALL_LASERS = (1 << 14) - 1
    game.state_machine.enter_game_select()
    gs = game.state_machine.program
    step(0)
    step(1 << 12)      # first press -> announce + arm reboot
    check("press btn12 -> armed 12", gs.armed == 12)
    check("system arm lights only slot 12", game.lasers.to_word() == (1 << 12))
    check("system arm not yet committed", gs.power_committed is False)
    step(0)
    step(1 << 0)       # a menu button cancels the power arm AND arms itself
    check("menu button cancels power arm + re-arms to it", gs.armed == 0)
    check("re-armed button lights its own laser", game.lasers.to_word() == (1 << 0))
    check("still GameSelect after cancel", prog() == "GameSelect")
    check("not committed after cancel", gs.power_committed is False)

    # 8b. an *unassigned* button cancels the power arm without re-arming.
    game.state_machine.enter_game_select()
    gs = game.state_machine.program
    step(0)
    step(1 << 12)      # arm reboot again
    check("re-armed btn12", gs.armed == 12)
    step(0)
    step(1 << 9)       # unassigned -> cancels, nothing re-armed
    check("unassigned button cancels power arm", gs.armed is None)
    check("unassigned cancel leaves lasers off", game.lasers.to_word() == 0)
    check("not committed after unassigned cancel", gs.power_committed is False)

    # 9. system slot (btn13 shutdown): three presses execute (simulated under -s)
    step(0)
    step(1 << 13)      # press 1 -> announce + arm
    check("press1 btn13 -> armed 13", gs.armed == 13)
    check("press1 not committed", gs.power_committed is False)
    step(0)
    step(1 << 13)      # press 2 -> confirm-arm (all lasers lit)
    check("press2 still armed 13", gs.armed == 13)
    check("press2 lights all lasers", game.lasers.to_word() == ALL_LASERS)
    check("press2 not committed", gs.power_committed is False)
    step(0)
    step(1 << 13)      # press 3 -> execute (no real reboot: '-s' simulates)
    check("press3 commits power action", gs.power_committed is True)
    check("still GameSelect (simulated, no real shutdown)", prog() == "GameSelect")

    # 10. volume slots (buttons 10/11): instant ±10% steps, no arm/launch.
    game.state_machine.enter_game_select()
    gs = game.state_machine.program
    vol = game.volume
    ENDCAPS = (1 << 6) | (1 << 7)
    approx = lambda a, b: abs(a - b) < 1e-6

    def vstep(button):  # press + release a volume button
        step(1 << button); step(0)

    check("volume starts at DEFAULT 0.7", approx(vol.level, 0.7))

    step(1 << 11)      # press volume up (held)
    check("volume up -> 0.8", approx(vol.level, 0.8))
    check("volume press does not arm a slot", gs.armed is None)
    check("volume press stays in GameSelect", prog() == "GameSelect")
    check("bar matches level (laser word)", game.lasers.to_word() == gs._volume_bar_word())
    check("bar never lights the endcap ports", (game.lasers.to_word() & ENDCAPS) == 0)
    step(0)

    vstep(11); vstep(11)  # 0.9, then 1.0 (max)
    check("volume up clamps at max 1.0", approx(vol.level, 1.0))
    check("is_max at 1.0", vol.is_max)
    step(1 << 11); # one more press at max: stays 1.0, bar = all in-line ports
    check("at max, bar lights all 12 in-line ports",
          game.lasers.to_word() == (((1 << 14) - 1) ^ ENDCAPS))
    step(0)

    for _ in range(10):   # walk all the way down to mute
        vstep(10)
    check("volume down clamps at mute 0.0", approx(vol.level, 0.0))
    check("is_muted at 0.0", vol.is_muted)
    step(1 << 10); # press down again while muted: bar is dark
    check("muted bar lights no lasers", game.lasers.to_word() == 0)
    step(0)

    # a persisted level survives a fresh VolumeController reading the same file
    from src.system_volume import VolumeController
    vstep(11)  # 0.0 -> 0.1 (a change, so it's saved)
    check("level persisted to state file", approx(VolumeController().level, vol.level))

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
