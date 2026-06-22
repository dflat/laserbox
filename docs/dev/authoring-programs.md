# Authoring new programs

This is the practical guide to writing a new game (a `Program`) for laserbox.
Read {doc}`state-machine` first for the lifecycle; this page is the how-to.

A complete, runnable template lives at `src/programs/example_program.py`
({class}`src.programs.example_program.ExampleProgram`). Copy it and adapt. The
sections below explain each piece.

## 1. The minimal skeleton

```python
from .base import *               # Program, State, StateMachine, StateSequence
from ..event_loop import *        # EventType, events, ToggleEvent, ...
from ..config import config

class MyGame(Program):
    def __init__(self):
        super().__init__()        # registers this singleton; sets up tick/scheduler/cooldowns

    def start(self):
        # called every time the program is activated
        self.game.lasers.set_word(0)

    def update(self, dt):
        super().update(dt)        # REQUIRED: runs cooldown/scheduler bookkeeping
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self.game.lasers.turn_on(event.key)
            elif event.type == EventType.BUTTON_UP:
                self.game.lasers.turn_off(event.key)

MyGame()                          # instantiate once at import → registers the program
```

Two non-negotiables:

1. **Call `super().__init__()`** in `__init__` and **`super().update(dt)`** at
   the top of `update` — otherwise registration, cooldowns, and the `after()`
   scheduler won't work.
2. **Instantiate the class once** at the bottom of the module. Construction is
   what registers it with the state machine.

Then make it importable by adding it to `src/programs/__init__.py`:

```python
from .my_game import MyGame
```

## 2. The lifecycle hooks

| Hook | When | Do |
|------|------|-----|
| `__init__(self)` | once, at import | `super().__init__()`; set *static* data only. `self.game` does **not** exist yet. |
| `start(self, **kwargs)` | each activation | load audio, set initial lasers, init round state. `kwargs` come from the context. |
| `update(self, dt)` | every frame | `super().update(dt)`; read events; drive game logic. `dt` is **milliseconds**. |
| `quit(self)` | to finish | optional cleanup, then `super().quit()` to advance the context. |
| `teardown(self)` | on switch-away (called *for* you) | override only for unusual resources; call `super().teardown()`. |

```{note}
The state machine sets `self.game` and `self.input_manager` (via
`make_active_program`) *before* `start()` is called, so they are available in
`start` and `update` but not in `__init__`.
```

## 3. Reading input

Input arrives as events on the global `events` queue. Drain it once per frame:

```python
for event in events.get():
    if event.type == EventType.BUTTON_DOWN:
        button_id = event.key          # 0..13
        toggles = event.state.toggles  # full State at the time of the event
    elif event.type == EventType.BUTTON_UP:
        ...
    elif isinstance(event, ToggleEvent):   # catches ToggleOn + ToggleOff
        toggles = self.game.input_manager.state.toggles  # current toggle state (0..3)
```

Event types: `BUTTON_DOWN`, `BUTTON_UP`, `TOGGLE_ON`, `TOGGLE_OFF` (see
{class}`src.event_loop.EventType`). Every input event carries:

- `event.key` — the button id (0–13) or toggle id (0–1),
- `event.state` — the full {class}`~src.programs.base.State` snapshot.

For the *current* live state regardless of events, use
`self.game.input_manager.state`.

```{important}
**The entry gesture reserves some input mid-game.** Buttons 0 & 1 + toggle 0 are
the default GameSelect gesture ({doc}`state-machine`). Your game still receives
those events normally, but be aware the operator can use that combination to
jump to the menu at any time.
```

## 4. Driving the lasers

Write to `self.game.lasers`, a {class}`src.game_loop.LaserBay`:

```python
self.game.lasers.turn_on(i)        # one laser on  (i = 0..13)
self.game.lasers.turn_off(i)
self.game.lasers.set_value(i, 1)   # on/off by value
self.game.lasers.set_word(0b101)   # whole field at once (bit i = laser i)
```

You set the field every frame as you like; `Game.render()` collapses it to one
word and pushes it (skipping the write when unchanged).

## 5. Playing audio

Through `self.game.mixer` (a {class}`src.audio_utils.Mixer`). Three kinds:

```python
# music: one looping background track from assets/music
self.game.mixer.load_music("Golf2Slow.wav", loops=-1)

# effects: one-shot sounds from assets/sounds/effects (subdirs ok)
self.game.mixer.load_effect("positive/hooray.wav", volume=0.4)
self.game.mixer.play_effect("positive/hooray.wav")

# patches: a 14-sound bank (one per button) from assets/sounds/patches
self.game.mixer.use_patch("numbers")
self.game.mixer.play_by_id(button_id)         # play sound N; duck=True dims music
```

See {doc}`audio` for the full model (ducking, sample-rate gotchas).

## 6. Timing helpers: cooldowns and `after()`

**Cooldowns** debounce/rate-limit a button:

```python
if button_id not in self.cooldowns:
    self.game.mixer.play_by_id(button_id)
    self.start_cooldown(button_id, ms=250)
```

**`after()`** schedules a deferred callback (great for "celebrate, then quit"):

```python
self.after(3000, self.quit)              # call self.quit() in 3 seconds
self.after(500, self.game.mixer.play_by_id, 0)   # args are forwarded
```

Both are **per-instance** and are flushed on teardown, so nothing leaks into the
next program.

## 7. Animations

Build a laser animation and `.start()` it; the global runner drives it and clears
the lasers when done (see {doc}`animation`):

```python
from ..animation import random_k_dance
random_k_dance(k=3, fps=8, dur=2.0).start()   # celebratory flashing
```

## 8. Finishing

Call `self.quit()` when the game is over. That advances the current context (or
returns to GameSelect if the context is done). Override `quit` to add cleanup:

```python
def quit(self):
    self.game.lasers.set_word(0)
    super().quit()
```

You generally **do not** need to stop your own audio/animations on quit — the
state machine's teardown does that. (You *can* fade music for a nicer
transition; several games do `pygame.mixer.music.fadeout(...)` before a delayed
`quit`.)

## 9. Making it selectable

To put your game in the operator menu, add it to
{class}`config.GameSelect.MENU <src.config.config.GameSelect>`:

```python
MENU = {
    ...
    5: ("MyGame", "my_game.wav"),   # (Program class name, announcement wav)
}
```

and drop the announcement WAV in `assets/sounds/effects/menu/` (22050 Hz / mono /
16-bit — see {doc}`audio` for the `edge-tts` recipe).

To include it in a scripted show, add its class name to a `Composer`'s
`program_name_sequence` (and matching `program_kwargs_sequence`); see
{class}`src.programs.base.BirthdayComposer`.

## 10. System assumptions & gotchas

- **`dt` is milliseconds.** Make time-based logic frame-rate independent; don't
  count frames for wall-clock durations (use `after()` or `time.time()`).
- **`config.FPS` differs by platform** (100 on the Pi, 60 on dev). Don't bake in
  a frame count that assumes one rate.
- **Always `super().update(dt)`** or cooldowns/`after()` silently stop working.
- **Don't rely on shared class state** for per-run data — `scheduler`/`cooldowns`
  are per-instance by design; keep your own run state on `self` and (re)init it
  in `start()`, since `start()` may be called many times.
- **A program can be interrupted at any frame** by the entry gesture. Don't
  assume `quit()` is the only way out; just make sure `start()` fully resets your
  state so a re-entry is clean.
- **The mixer can be re-initialised** by other programs (MusicMaker does), which
  invalidates cached `Sound`s. Load the audio you need in `start()`.

## 11. Testing your game

```bash
# Launch straight into it in the simulator (bypasses the menu):
python -m src -s -p MyGame
```

For logic you want to assert without a window, drive a `Game` with a scripted
input register (see `scratch/test_gameselect.py` for a working harness): set the
input word, call `game.update(dt)` / `game.render()`, and assert on
`game.state_machine.program` and `game.lasers.to_word()`. Run it headless with
`SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy`.
