"""Unit tests for the monotonic time system: :mod:`src.clock` + ``GameClock``.

These pin the invariants that the boot-time-timing bug violated:

* the loop is paced by a **monotonic** source and is wholly unaffected by
  wall-clock (``time.time``) jumps;
* ``GameClock`` holds the target frame rate when frames are cheap;
* after a large gap (a stall, or any clock anomaly) it **resyncs instead of
  free-running to catch up**, and never emits a runaway ``dt``.

Everything is driven by a deterministic ``FakeClock`` (no real sleeping), so the
tests are fast and reproducible. Run from repo root:

    SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python3 scratch/test_clock.py
"""
import os
import sys
import time as real_time

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = [sys.argv[0], "-s"]

from src import clock
from src.game_loop import GameClock


class FakeClock:
    """A controllable monotonic clock; ``sleep`` simply advances it (no waiting)."""
    def __init__(self, t=1000.0):
        self.t = t

    def monotonic(self):
        return self.t

    def sleep(self, secs):
        # A real sleep advances wall time; the fake one advances our timeline.
        if secs > 0:
            self.t += secs

    def advance(self, secs):
        self.t += secs


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label)


def with_fake(fake):
    """Point the clock module at ``fake`` for the duration of a test block."""
    return clock.set_source(fake.monotonic, fake.sleep)


def test_clock_module_basics():
    fake = FakeClock(t=500.0)
    restore = with_fake(fake)
    try:
        check("monotonic() reads the source", clock.monotonic() == 500.0)
        check("monotonic_ms() is seconds*1000", clock.monotonic_ms() == 500_000.0)
        clock.sleep(2.0)
        check("sleep() advances the fake clock", clock.monotonic() == 502.0)
        clock.sleep(-5)  # non-positive sleeps are a no-op, never go backwards
        check("negative sleep is a no-op", clock.monotonic() == 502.0)
    finally:
        restore()
    check("set_source restore() puts the real source back",
          clock.monotonic() != 502.0)


def test_paced_when_frames_are_cheap():
    """Cheap frames (no work) => the clock sleeps to hold exactly target dt."""
    fake = FakeClock()
    restore = with_fake(fake)
    try:
        fps = 100
        gc = GameClock(fps)
        dts = [gc.tick() for _ in range(200)]
        steady = dts[5:]  # ignore the first couple while the schedule settles
        target_ms = 1000.0 / fps
        ok = all(abs(dt - target_ms) < 1e-6 for dt in steady)
        check("cheap frames are paced to the target dt (10ms @100fps)", ok)
        check("reported dt is in milliseconds", abs(steady[0] - 10.0) < 1e-6)
    finally:
        restore()


def test_work_heavier_than_budget_runs_uncapped_but_truthful():
    """When a frame's real work exceeds the budget, we don't sleep, and dt is
    the true elapsed time (no negative/zero waits, no inflation)."""
    fake = FakeClock()
    restore = with_fake(fake)
    try:
        gc = GameClock(100)  # 10ms budget
        # Simulate 7ms of real work per frame (under budget): expect ~10ms pacing.
        for _ in range(20):
            fake.advance(0.007)
            dt = gc.tick()
        check("under-budget work still paced to ~10ms", abs(dt - 10.0) < 1e-6)
        # Now 25ms of work per frame (over the 10ms budget, under the 50ms clamp).
        for _ in range(20):
            fake.advance(0.025)
            dt = gc.tick()
        check("over-budget frames report their true ~25ms dt (uncapped, not 10)",
              abs(dt - 25.0) < 1e-6)
    finally:
        restore()


def test_no_catch_up_burst_after_a_large_gap():
    """The core fix: a huge gap (long stall, or what a wall-clock leap *used* to
    do) must NOT trigger a free-run burst of zero-sleep frames. The schedule
    resyncs, dt is clamped, and the very next frames are paced normally again."""
    fake = FakeClock()
    restore = with_fake(fake)
    try:
        fps = 100
        gc = GameClock(fps)
        for _ in range(10):
            gc.tick()  # warm up, steady state

        # A 15-minute gap appears between frames (e.g. the process was frozen, or
        # -- in the old time.time() design -- NTP stepped the clock mid-session).
        fake.advance(900.0)
        dt_gap = gc.tick()
        check("dt across a huge gap is CLAMPED, not 900_000ms",
              dt_gap <= 1000.0 * gc.max_lag + 1e-6)

        # Crucially, the loop does not now free-run to 'catch up' 90,000 frames.
        # Each subsequent cheap frame sleeps the fake clock forward by ~target_dt;
        # a catch-up burst would instead advance it by ~0 for thousands of frames.
        before = fake.monotonic()
        for _ in range(100):
            gc.tick()
        advanced = fake.monotonic() - before
        expected = 100 * gc.target_dt
        check("100 frames after the gap advance ~1s of real time (paced, not free-run)",
              abs(advanced - expected) < 0.05)
    finally:
        restore()


def test_immune_to_wall_clock_jumps():
    """Pacing must not depend on time.time() at all: stepping the wall clock by
    days, forward or backward, changes nothing about the loop's timing."""
    fake = FakeClock()
    restore = with_fake(fake)
    saved_time = real_time.time
    try:
        gc = GameClock(100)
        for _ in range(10):
            gc.tick()
        # Wildly corrupt the wall clock both directions; GameClock must ignore it.
        real_time.time = lambda: 0.0
        dt1 = gc.tick()
        real_time.time = lambda: 9.99e12
        dt2 = gc.tick()
        check("dt unaffected by a backward wall-clock jump", abs(dt1 - 10.0) < 1e-6)
        check("dt unaffected by a forward wall-clock jump", abs(dt2 - 10.0) < 1e-6)
    finally:
        real_time.time = saved_time
        restore()


def main():
    test_clock_module_basics()
    test_paced_when_frames_are_cheap()
    test_work_heavier_than_budget_runs_uncapped_but_truthful()
    test_no_catch_up_burst_after_a_large_gap()
    test_immune_to_wall_clock_jumps()

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
