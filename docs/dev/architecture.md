# Architecture

This page is the mental model. Read it once and the rest of the codebase will
make sense.

## The big picture

laserbox is a fixed-timestep game loop. Every frame it does the same four
things, in order:

```
   ┌─────────────────────────────────────────────────────────────┐
   │                        Game.update(dt)                        │
   │                                                               │
   │  1. InputManager.poll()      read register → diff → events    │
   │  2. Animation.update_all()   advance any running animations   │
   │  3. StateMachine.update()    (gesture check) → Program.update │
   │                                                               │
   │                        Game.render()                          │
   │  4. OutputManager.push_word(LaserBay.to_word())               │
   └─────────────────────────────────────────────────────────────┘
                 paced by GameClock.tick() → target FPS
```

The same `Game` runs on the Pi and (subclassed as `Simulator`) on the desktop;
only the register implementations differ.

## The pieces

```
        hardware                 engine                        game
   ┌───────────────┐      ┌───────────────────┐        ┌─────────────────┐
   │ 74HC165 (in)  │─────▶│ InputShiftRegister │──poll─▶│  InputManager   │
   └───────────────┘      └───────────────────┘        │  → events queue │
                                                        └────────┬────────┘
                                                                 │ events
                                                        ┌────────▼────────┐
                                                        │  StateMachine   │
                                                        │  → Program      │
                                                        └────────┬────────┘
                                                                 │ writes
   ┌───────────────┐      ┌───────────────────┐        ┌────────▼────────┐
   │ 74HC595 (out) │◀─────│OutputShiftRegister │◀─push─│    LaserBay     │
   └───────────────┘      └───────────────────┘        └─────────────────┘
```

- **{doc}`hardware` drivers** ({mod}`src.shift_register`) — bit-bang the two
  registers. The input register yields a 16-bit word; the output register
  accepts one.
- **I/O managers** ({mod}`src.io_managers`) — `InputManager` polls the register,
  diffs the new word against the last, and turns each changed bit into an
  event. `OutputManager` pushes the laser word, skipping the write if it is
  unchanged.
- **Event loop** ({mod}`src.event_loop`) — a singleton queue (`events`) plus a
  bounded history. Input becomes `ButtonDown/Up` and `ToggleOn/Off` events; the
  active program drains the queue each frame.
- **State machine & programs** ({mod}`src.programs.base`) — owns the one active
  `Program` and routes between programs. Covered in {doc}`state-machine`.
- **Laser output** (`LaserBay` in {mod}`src.game_loop`) — programs write here
  (per-laser or whole-word); each frame it collapses to a single 16-bit word.
- **Audio** ({mod}`src.audio_utils`) — music, one-shot effects, and 14-sound
  "patches". See {doc}`audio`.
- **Animations** ({mod}`src.animation`) — time-driven laser sequences that write
  to the `LaserBay`. See {doc}`animation`.

## The frame loop in detail

`Game.run()` ({class}`src.game_loop.Game`) loops forever:

```python
while True:
    self.update(dt)
    self.render()
    dt = self.clock.tick(self.FPS)   # sleep to hold target FPS; return real dt (ms)
```

`dt` is the real elapsed milliseconds for the previous frame, threaded through
to programs and animations so timing is frame-rate independent.

### 1. Input → events

`InputManager.poll()` reads a fresh {class}`src.programs.base.State` (a wrapper
around the 16-bit word: low 14 bits = buttons, top 2 = toggles). If the word
changed, it XORs against the previous word to find the bits that flipped on and
off, and pushes one event per changed bit onto the `events` queue. It also keeps
a `changed_state` flag and a short state history.

### 2. Animations

`Animation.update_all(dt)` advances every running animation. Animations write
laser words directly into the shared `LaserBay`, independently of whatever the
active program is doing.

### 3. State machine → program

`StateMachine.update(dt)` first feeds the latest state to the global
{class}`src.programs.base.GestureDetector` (the GameSelect entry gesture — see
{doc}`state-machine`); if it fires, control jumps to the menu. Otherwise it
calls `self.program.update(dt)`, and the active program drains the event queue
and does its thing.

### 4. Output

`Game.render()` calls `LaserBay.to_word()` (cached unless something changed) and
hands it to `OutputManager.push_word()`, which writes to the register only when
the word differs from the last push.

## Timing model

{class}`src.game_loop.GameClock` is a fixed-timestep pacer. It tracks a *target
playhead* (`frame * target_dt`) against the *actual* elapsed time and sleeps to
absorb the difference, so the loop holds a steady FPS without drifting fast.
`config.FPS` is 100 on the Pi (low input latency) and 60 elsewhere.

## Threads

The loop is single-threaded. The one exception is audio "ducking"
({meth}`src.audio_utils.Mixer.duck_for_sound`), which briefly lowers music
volume under a voice clip on a background thread. Everything else — input,
state, lasers — happens on the main loop.
