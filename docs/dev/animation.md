# Animations

Animations are time-driven laser sequences. They live in {mod}`src.animation`
and write directly to the shared `LaserBay`, independent of the active program.

## Model

- {class}`~src.animation.Frame` — one step: a laser `word` (and/or an effect
  `sound`).
- {class}`~src.animation.FrameSequence` — an ordered list of frames plus a
  per-frame **timing track** (milliseconds). Build evenly-timed sequences with
  `FrameSequence.by_fps(frames, fps)` or `FrameSequence.by_dur(frames, dur)`.
- {class}`~src.animation.DynamicFrameSequence` — frames generated on the fly by a
  `func(frame) -> Frame` at playback time (e.g. random flashes).
- {class}`~src.animation.Animation` — plays a sequence over time.

## Running one

Build an animation and call `.start()`. The global runner
({meth}`Animation.update_all <src.animation.Animation.update_all>`, called each
frame by `Game.update`) advances every running animation and reaps finished
ones. When an animation ends, its `done()` hook runs (the default clears the
lasers).

```python
from ..animation import random_k_dance
anim = random_k_dance(k=3, fps=8, dur=2.0)
anim.start()
```

`loops` controls repetition: `0` plays once, `n` plays `n` extra times, `-1`
loops forever (used for "hold" patterns). A forever-looping animation is stopped
either by `anim.kill()` or, automatically, by the state machine's teardown when
the program switches.

## Built-in factories

| Factory | Effect |
|---------|--------|
| {func}`~src.animation.hold_pattern` | Slowly cycles a fixed list of words; loops forever. Used as a waiting/idle pattern. |
| {func}`~src.animation.ping_pong` | A single lit laser sweeps up the ports and back. |
| {func}`~src.animation.random_k_dance` | Flashes `k` random lasers per frame for `dur` seconds; the standard celebration. |

## Customising

Subclass {class}`~src.animation.Animation` (or pass callbacks) and override
`set_up` (run-once), `play_frame` (render a frame), and/or `done` (end hook).
`play_frame` reads `self.frames[self.frame_no]`, applies the sequence's optional
`func`, then writes the frame's `word` to the lasers and plays its `sound`.

```{note}
The `game` reference animations use to reach the lasers/mixer is injected once on
the **class** (`Animation.game`) by `Game.__init__`, so any animation can drive
output without being handed a game instance.
```

## Teardown interaction

{meth}`Animation.kill_all <src.animation.Animation.kill_all>` immediately stops
every running animation (without firing `done` callbacks). The state machine
calls it on every program switch so a previous game's animation can't keep
driving the lasers into the next program.
