# Time and timing

Everything in laserbox that measures a **duration** or schedules a **deadline**
goes through one timeline. This page explains what that timeline is, why it is
built the way it is, and the rule you must follow when writing a game.

## The one rule

> **Measure time with `self.now_ms` (in a `Program`) or `src.clock`. Never use
> `time.time()`.**

`time.time()` is the *wall clock*. On the box it is not trustworthy, and using
it to measure how long something took will silently corrupt your timing.

## Why `time.time()` is poison here

The box is a Raspberry Pi with **no battery-backed real-time clock**. At boot the
system clock starts at a stale value restored by `fake-hwclock` (the time of the
last shutdown), and the app **auto-starts immediately**. Some seconds later, once
the network is up, `systemd-timesyncd` contacts an NTP server and **steps the
clock forward** to the true time — a jump that can be seconds, minutes, or more.

If anything sampled `time.time()` *before* that step and measured against it
*after*, the measured "elapsed time" includes the whole jump. The old game loop
paced itself against `time.time()`, so on the unlucky boots where the step landed
mid-session the loop concluded it was wildly behind schedule and **free-ran to
catch up**, running hundreds of frames per second. Because every in-game timeout
was counted in *frames*, the GameSelect arm window and Trivia's buzz/answer
windows collapsed from tens of seconds to a fraction of a second — and stayed
broken for the rest of that session. Other boots, where the step happened before
the app started, were fine. That is the bug this whole subsystem prevents.

## The three layers

```
   time.monotonic()            ← only ever moves forward, steady rate, no jumps
        │   wrapped by
        ▼
   src.clock                    monotonic(), monotonic_ms(), sleep()
        │   used by
        ▼
   GameClock.tick()             paces the loop to FPS; returns each frame's real dt (ms)
        │   summed by
        ▼
   Game.now_ms                  monotonic ms since the loop started
        │   read as
        ▼
   Program.now_ms               what your game sets and checks deadlines against
```

* **`src.clock`** is the single authoritative source, backed by
  `time.monotonic()`. A monotonic clock cannot be stepped by NTP or `date`, so
  durations measured through it are always honest. Tests swap in a fake clock via
  `clock.set_source(...)`.

* **`GameClock`** paces the main loop. It sleeps until each frame's scheduled
  time and reports the frame's *real* elapsed `dt`. It deliberately does **not**
  try to "make up" lost time: if the loop falls more than `MAX_FRAME_SKIP` frames
  behind (a long stall, or any clock anomaly), it drops the backlog and resyncs,
  and clamps the returned `dt`. So a one-off hitch can never trigger a free-run
  burst or inject a giant time step into game logic.

* **`Game.now_ms`** accumulates those real `dt` values into a millisecond
  timeline, advanced once at the top of every `Game.update(dt)`. It is frozen for
  the duration of a frame, so every deadline you set or check within one frame
  sees a consistent "now".

## Writing timing code in a game

Set a deadline by adding a millisecond duration to `self.now_ms`, and check it by
comparing against `self.now_ms`:

```python
def start(self):
    self.deadline = self.now_ms + 5000        # 5 seconds from now

def update(self, dt):
    super().update(dt)
    if self.now_ms > self.deadline:
        self.times_up()
```

For one-shot callbacks and debounces, use the helpers on `Program`, which are
built on the same timeline:

```python
self.after(1500, self.reveal_answer)          # run 1.5 s from now
self.start_cooldown(button_id, ms=120)        # ignore re-presses for 120 ms
```

`self.tick` still exists as a **frame counter**, but it is *not* a clock — it
only counts frames, which drift relative to real time. Never use it for a
timeout; use `now_ms`.

Code that runs **off** the game loop (e.g. the audio-fade worker thread) has no
`now_ms` to read, so it calls `clock.monotonic()` directly. That is the only
place outside the loop that touches time, and it still never touches the wall
clock.

## Tests

The invariants live in two headless tests (see {doc}`simulator` for how to run
the suite):

- `scratch/test_clock.py` — unit tests for `src.clock` and `GameClock`: pacing,
  the no-catch-up-burst guarantee, dt clamping, and immunity to `time.time()`
  jumps, all driven by a deterministic fake clock.
- `scratch/test_timeouts.py` — integration tests proving an in-game window lasts
  its configured **milliseconds** regardless of frame rate, and that a simulated
  NTP-style wall-clock leap mid-session does **not** shorten it.
