# Simulator & dev workflow

The simulator lets you run the entire game on a desktop, with no Pi and no
wiring. It lives in {mod}`src.simulator.simulator`.

## Running

```bash
python -m src -s            # boot into GameSelect, in a pygame window
python -m src -s -p Golf    # boot straight into one program
```

The `-s` flag selects the simulator (and also skips the `RPi.GPIO` import, which
only exists on the Pi). `-p <Program>` launches a single program by class name.

## How it works

{class}`~src.simulator.simulator.Simulator` subclasses
{class}`src.game_loop.Game`, swapping the real shift registers for dummies:

- {class}`~src.simulator.simulator.DummyInputShiftRegister` reads the keyboard
  via pygame and exposes the same `read_word()` the engine expects.
- {class}`~src.simulator.simulator.DummyOutputShiftRegister` maps the pushed
  laser word onto on-screen {class}`~src.simulator.simulator.LaserPort` views.
- {class}`~src.simulator.simulator.DummyLaserBay` lays the 14 ports out as the
  physical floor (two rows of six, plus two side lasers).

Because only the registers differ, **the engine, programs, audio, and state
machine all run exactly as they do on the box.**

## Keyboard mapping

Keys `0`–`9` and `a`–`f` map (hex) to the 16 input bits:

| Key(s) | Input |
|--------|-------|
| `0`–`9`, `a`–`d` | buttons 0–13 (momentary: on while held) |
| `e` | toggle 0 (flips state on each press) |
| `f` | toggle 1 (flips state on each press) |

So, for example, to trigger the **GameSelect entry gesture** from inside a game:
hold `0` and `1`, then tap `e` twice.

## Headless logic tests

For deterministic tests without a window or audio device, construct a `Game`
with a scripted input register, step frames, and assert on state. See
`scratch/test_gameselect.py` for a complete example. Run headless with dummy SDL
drivers:

```bash
SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_gameselect.py
```

This pattern is the recommended way to test program/state-machine logic.

## Screenshots

`scratch/sim_screenshot.py` boots the simulator, captures the window with
`grim`, and shuts it down — handy for a quick visual smoke check on a Wayland
desktop.
