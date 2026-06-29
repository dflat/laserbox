"""
Headless logic smoke test for the WhackAMole feature.

Drives a real Game with a scripted input register (no display/keyboard needed),
stepping frames and asserting mode selection, spawning, hit scoring, fair
half-balance, and winner resolution. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python scratch/test_whack_a_mole.py
"""
import json
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

# Point the persistent high-score file at a throwaway temp path so the test is
# hermetic (never touches a real box's records).
_HS = os.path.join(tempfile.mkdtemp(prefix="whack_hs_"), "whack_a_mole.json")
config.WhackAMole.HIGHSCORE_PATH = _HS


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
    check("new-highscore clip loaded", prog().new_highscore in fx)
    check("new-record clip loaded", prog().new_record_vo in fx)
    check("starts with a fresh (zeroed) score board",
          prog().scores == {"solo_best": 0, "versus_best": 0})

    # spoken result readout: "<who> hit N mole(s) and got M miss(es)" (Trivia-style)
    p0 = prog()
    check("hit lead-ins loaded",
          all(n in fx for n in (p0.you_hit, p0.player_1_hit, p0.player_2_hit)))
    check("number bank loaded (incl. hundreds)",
          all(f"whack/num/{v}.wav" in fx for v in (0, 7, 19, 20, 90, 9, 100, 200)))
    check("single-digit -> one clip", p0._number_clips(7) == ["whack/num/7.wav"])
    check("teen -> one clip", p0._number_clips(19) == ["whack/num/19.wav"])
    check("round ten -> one clip", p0._number_clips(50) == ["whack/num/50.wav"])
    check("compound -> tens + ones",
          p0._number_clips(47) == ["whack/num/40.wav", "whack/num/7.wav"])
    check("99 composes", p0._number_clips(99) == ["whack/num/90.wav", "whack/num/9.wav"])
    check("zero speaks", p0._number_clips(0) == ["whack/num/0.wav"])
    # hundreds place
    check("100 -> one clip", p0._number_clips(100) == ["whack/num/100.wav"])
    check("147 -> hundreds + tens + ones",
          p0._number_clips(147) == ["whack/num/100.wav", "whack/num/40.wav", "whack/num/7.wav"])
    check("200 -> one clip", p0._number_clips(200) == ["whack/num/200.wav"])
    check("215 -> hundreds + teen", p0._number_clips(215) == ["whack/num/200.wav", "whack/num/15.wav"])
    check("clamps above 299",
          p0._number_clips(350) == ["whack/num/200.wav", "whack/num/90.wav", "whack/num/9.wav"])

    # hit readout: lead-in + count + mole/moles (singular only at exactly one)
    check("hit words loaded", all(n in fx for n in (p0.mole_word, p0.moles_word)))
    check("one hit -> 'You hit' + singular mole",
          p0._hits_clips(p0.you_hit, 1) == [p0.you_hit, "whack/num/1.wav", p0.mole_word])
    check("several hits -> lead + plural moles",
          p0._hits_clips(p0.player_1_hit, 5)
          == [p0.player_1_hit, "whack/num/5.wav", p0.moles_word])
    check("zero hits -> plural moles",
          p0._hits_clips(p0.you_hit, 0) == [p0.you_hit, "whack/num/0.wav", p0.moles_word])

    # miss readout: 'perfect game' at zero, else 'and got' + count + miss/misses
    check("miss clips loaded",
          all(n in fx for n in (p0.perfect_game, p0.and_got, p0.miss_word, p0.misses_word)))
    check("zero misses -> perfect game", p0._misses_clips(0) == [p0.perfect_game])
    check("one miss -> 'and got' + singular",
          p0._misses_clips(1) == [p0.and_got, "whack/num/1.wav", p0.miss_word])
    check("several misses -> 'and got' + plural",
          p0._misses_clips(3) == [p0.and_got, "whack/num/3.wav", p0.misses_word])

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

    # run a while so spawns/expiries cycle; moles must stay on the left half, and
    # the count must *vary* between 1 and SINGLE_MAX_MOLES (no longer stuck at one)
    max_moles = len(p.moles)
    only_left = True
    for _ in range(400):
        step(0)
        max_moles = max(max_moles, len(p.moles))
        only_left = only_left and all(port in p.left_ports for port in p.moles)
    check("after play, still only left-half moles", only_left)
    check("left half actually spawned moles", p.spawn_count["left"] > 0)
    check("1-player runs more than one mole at a time", max_moles >= 2)
    check("1-player never exceeds SINGLE_MAX_MOLES", max_moles <= p.single_max)
    check("unwhacked moles count as misses", p.misses["left"] > 0)

    # whack a live mole -> score increments, that mole clears. The 1-player board
    # can be momentarily empty between a spawn tick and the next, so guarantee a
    # live mole rather than depending on where the random run loop happened to end.
    if not p.moles:
        p._spawn_one(*p.sides[0])
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
    check("2-player tracks misses per half",
          p.misses["left"] > 0 and p.misses["right"] > 0)

    # --- winner resolution + the bay clears at the buzzer ---
    # player 1 (left) ahead
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)                      # white -> multi
    p.score = {"left": 5, "right": 3}
    p._congrats_dur = 0.05
    p._end_round()
    check("L>R -> RESULT", p.phase == "RESULT")
    check("L>R -> left wins", p._winner == "left")
    check("laser bay cleared the moment the round ends", game.lasers.to_word() == 0)

    # player 2 (right) ahead
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)
    p.score = {"left": 1, "right": 6}
    p._congrats_dur = 0.05
    p._end_round()
    check("R>L -> right wins", p._winner == "right")

    # equal scores -> tie
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)
    p.score = {"left": 4, "right": 4}
    p._congrats_dur = 0.05
    p._end_round()
    check("equal scores -> tie", p._winner == "tie")

    # --- a press on an empty hole is harmless (no score, no crash) ---
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 2); step(0)                      # black -> single
    p.moles = {}                               # clear the board
    empty_port = 6
    step(1 << empty_port)
    check("empty-hole press does not score", p.score["left"] == 0)

    # --- score tracker: solo personal best persists + fanfares on a break ---
    def read_scores():
        with open(_HS) as f:
            return json.load(f)

    def wipe_board():
        try:
            os.remove(_HS)
        except FileNotFoundError:
            pass

    wipe_board()                               # start from an empty board
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 2); step(0)                      # black -> single
    check("fresh launch zeroes solo_best", p.scores["solo_best"] == 0)
    p.score = {"left": 12}
    p._congrats_dur = 0.05
    p._end_round()
    check("solo beats record -> solo_best updates", p.scores["solo_best"] == 12)
    check("beating the record sets _broke_record", p._broke_record is True)
    check("solo_best persisted to disk", read_scores().get("solo_best") == 12)

    # relaunch -> the saved personal best loads back from disk
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    check("persisted solo_best loads on relaunch", p.scores["solo_best"] == 12)

    # a weaker solo round does NOT lower the record and does not fanfare
    step(1 << 2); step(0)
    p.score = {"left": 5}
    p._congrats_dur = 0.05
    p._end_round()
    check("weaker solo round keeps the record", p.scores["solo_best"] == 12)
    check("no record broken on a weaker round", p._broke_record is False)

    # --- score tracker: 2-player all-time best (versus_best) ---
    wipe_board()
    game.state_machine.launch_single_program("WhackAMole")
    p = prog()
    step(1 << 9); step(0)                      # white -> multi
    p.score = {"left": 8, "right": 3}
    p._congrats_dur = 0.05
    p._end_round()
    check("2-player best side sets versus_best", p.scores["versus_best"] == 8)
    check("versus_best persisted to disk", read_scores().get("versus_best") == 8)
    check("winner resolved alongside a record", p._winner == "left")

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
