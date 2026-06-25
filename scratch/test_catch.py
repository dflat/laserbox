"""Headless logic smoke test for the Catch mini-game.

Drives a real Game with a scripted input register (no display/keyboard) and
asserts the intro, a press-to-skip-intro, the READY -> auto-start -> CHASE flow,
any-button catch-to-climb a level, miss-back-to-level-1 (with no repeated level-1
cue), the final-level win -> menu, and the blip bounce. Scheduled
``after()`` transitions run on wall-clock time, so where a test needs the far
side of one it calls the transition method directly. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python scratch/test_catch.py
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

    cfg = config.Catch
    target = cfg.TARGET
    last = cfg.N_PORTS - 1
    n_levels = len(cfg.LEVEL_STEP_MS)

    def prog():
        return game.state_machine.program

    def step(word):
        piso.word = word
        game.update(dt)
        game.render()

    passed = []
    def check(label, cond):
        passed.append(bool(cond))
        print(("PASS" if cond else "FAIL"), "-", label)

    # Capture which effect each phase plays (avoids needing real audio output).
    played = []
    game.mixer.play_effect = lambda name, **k: played.append(name)

    def arm_chase(blip, level):
        """Force a clean CHASE at ``level`` with the blip parked at ``blip``."""
        step(0)  # release any held button so the next press is a real edge
        p = prog()
        p.scheduler = []          # drop any pending scheduled transition
        p.state = p.CHASE
        p.level_index = level
        p.blip = blip
        p.blip_dir = 1
        p._blip_accum_ms = 0.0
        p._clock_ms = 0.0  # start on a lit blink flash for deterministic renders
        played.clear()

    # config sanity: one announcement per level
    check("a level announcement per level", len(cfg.LEVEL_SOUNDS) == n_levels)

    # 1. launch -> Catch, intro plays, READY (target preview, no press-to-begin)
    game.state_machine.launch_single_program("Catch")
    check("launched Catch", prog().__class__.__name__ == "Catch")
    check("intro plays on start", cfg.INTRO_SOUND in played)
    check("starts in READY", prog().state == "READY")

    # 2. during the intro, only the target laser blinks (no other bit ever set)
    step(0)
    check("READY lights only the target", game.lasers.to_word() == (1 << target))
    prog()._clock_ms = prog().blink_half_period_ms + 1  # push into the dark half
    step(0)
    check("READY target blink goes dark", game.lasers.to_word() == 0)

    # 3. a press during the intro skips it and starts level 1 right away
    played.clear()
    step(1 << 5)  # any button skips the rest of the narration
    check("press during READY skips intro -> PAUSE", prog().state == "PAUSE")
    check("skip announces level 1", played and played[-1] == cfg.LEVEL_SOUNDS[0])
    check("skip starts at level index 0", prog().level_index == 0)

    # 4. without a skip, level 1 starts on its own when the intro finishes
    game.state_machine.launch_single_program("Catch")  # fresh READY
    check("re-launch back to READY", prog().state == "READY")
    played.clear()
    prog()._enter_level(0)  # far side of the scheduled intro -> level 1
    check("auto-start -> PAUSE (level cue)", prog().state == "PAUSE")
    check("level-1 announced", played and played[-1] == cfg.LEVEL_SOUNDS[0])
    check("level index is 0", prog().level_index == 0)
    prog()._start_chase()  # far side of the scheduled hold
    check("after the hold -> CHASE", prog().state == "CHASE")
    check("blip spawns at port 0", prog().blip == 0)

    # 5. CATCH on a non-final level climbs one level (announced)
    arm_chase(blip=target, level=0)
    step(1 << target)
    check("catch on level 0 -> PAUSE", prog().state == "PAUSE")
    check("climbed to level index 1", prog().level_index == 1)
    check("level-2 announced on climb", played[-1] == cfg.LEVEL_SOUNDS[1])

    arm_chase(blip=target, level=1)
    step(1 << target)
    check("catch on level 1 -> level index 2", prog().level_index == 2)
    check("level-3 announced on climb", played[-1] == cfg.LEVEL_SOUNDS[2])

    # 6. MISS: target press while the blip is elsewhere
    arm_chase(blip=target + 2, level=2)
    step(1 << target)
    check("blip elsewhere -> miss sound", played[-1] == cfg.MISS_SOUND)
    check("miss-hold shows missed blip + lit target",
          game.lasers.to_word() == ((1 << target) | (1 << (target + 2))))
    # the target keeps blinking through the hold while the missed blip stays solid
    prog()._clock_ms = prog().blink_half_period_ms + 1  # push into the dark half
    step(0)
    check("miss-hold: target blinks off, missed blip stays solid",
          game.lasers.to_word() == (1 << (target + 2)))
    played.clear()
    prog()._rearm()  # far side of the scheduled reset
    check("miss auto-restarts level 1 (PAUSE cue)", prog().state == "PAUSE")
    check("miss resets to level 0", prog().level_index == 0)
    check("level-1 cue NOT replayed on restart (miss line already said it)",
          cfg.LEVEL_SOUNDS[0] not in played)

    # 6b. any button (not just the target's own) catches on a winning blip
    arm_chase(blip=target, level=1)
    step(1 << 7)
    check("wrong button still catches when blip is on target",
          played[-1] == cfg.LEVEL_SOUNDS[2])
    check("any-button catch climbs a level", prog().level_index == 2)

    # 7. blip bounces at both ends and keeps going (no auto-stop)
    p = prog()
    p.state, p.blip, p.blip_dir = p.CHASE, last - 1, 1
    p._step_blip(); check("steps up to the last port", p.blip == last)
    p._step_blip(); check("reflects off the top", p.blip == last - 1 and p.blip_dir == -1)
    p.blip, p.blip_dir = 1, -1
    p._step_blip(); check("reflects off the bottom", p.blip == 0 and p.blip_dir == 1)
    p._step_blip(); check("keeps bouncing past 0", p.blip == 1 and p.state == "CHASE")

    # 8. CATCH on the final level wins, then returns to the menu (done last,
    #    since quitting tears Catch down)
    arm_chase(blip=target, level=n_levels - 1)
    step(1 << target)
    check("final-level catch -> win sound", played[-1] == cfg.WIN_SOUND)
    check("win freezes input (PAUSE)", prog().state == "PAUSE")
    prog().quit()  # far side of the scheduled celebrate-then-quit
    check("win returns to GameSelect", prog().__class__.__name__ == "GameSelect")

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
