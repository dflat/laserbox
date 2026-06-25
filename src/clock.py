"""The one authoritative time source for the whole codebase.

Everything that measures a *duration* or schedules a *deadline* reads time
through this module. It is backed by :func:`time.monotonic` -- a clock that only
ever moves forward, at a steady rate, and is **immune to wall-clock
adjustments**: NTP steps, a manual ``date`` change, or the RTC-less Pi's
boot-time clock jump when ``systemd-timesyncd`` first syncs.

**Never use** :func:`time.time` (the wall clock) to measure elapsed time. On the
box there is no battery-backed RTC, so at boot the clock starts at a stale
``fake-hwclock`` value and then *leaps forward* when the network comes up. Any
duration measured across that leap is corrupted. That bug used to compress every
frame-paced timeout (GameSelect's arm window, Trivia's buzz/answer windows) to a
fraction of a second on the unlucky boots where the leap landed mid-session.
See ``docs/dev/time.md``.

Two layers build on this module:

* :class:`~src.game_loop.GameClock` paces the main loop and reports each frame's
  real elapsed ``dt`` (in ms).
* :class:`~src.game_loop.Game` accumulates those ``dt`` values into ``now_ms`` --
  a monotonic millisecond timeline that every :class:`~src.programs.base.Program`
  reads (via ``self.now_ms``) to set and check deadlines.

Tests substitute a deterministic, controllable source with :func:`set_source`.
"""
import time as _time

# The live sources. Swapped out (only) by tests via :func:`set_source`.
_monotonic = _time.monotonic
_sleep = _time.sleep


def monotonic():
    """Seconds since an arbitrary fixed origin. Only ever increases."""
    return _monotonic()


def monotonic_ms():
    """Milliseconds since an arbitrary fixed origin. Only ever increases."""
    return _monotonic() * 1000.0


def sleep(seconds):
    """Block for ``seconds`` (a no-op for non-positive values).

    Routed through this module so a fake clock can drive the loop in tests
    without real wall-clock waiting.
    """
    if seconds > 0:
        _sleep(seconds)


def set_source(monotonic_fn=None, sleep_fn=None):
    """Replace the monotonic and/or sleep source. **Tests only.**

    Args:
        monotonic_fn: Zero-arg callable returning monotonic seconds, or None to
            leave the current source unchanged.
        sleep_fn: One-arg ``sleep(seconds)`` callable, or None to leave it.

    Returns:
        A zero-arg ``restore()`` that puts the previous sources back.
    """
    global _monotonic, _sleep
    prev = (_monotonic, _sleep)
    if monotonic_fn is not None:
        _monotonic = monotonic_fn
    if sleep_fn is not None:
        _sleep = sleep_fn

    def restore():
        global _monotonic, _sleep
        _monotonic, _sleep = prev

    return restore
