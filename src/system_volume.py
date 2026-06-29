"""OS-level master volume control (PipeWire via ``wpctl``).

The box plays through a USB DAC that PipeWire exposes as the default sink, so a
single ``wpctl set-volume @DEFAULT_AUDIO_SINK@`` call scales *everything* the app
outputs. That makes the OS sink the project's master volume: pygame offers only
per-:class:`~pygame.mixer.Sound` and music-stream gains (no master), so an
in-app master would mean threading a multiplier through every program and the
ducking code. Controlling the OS sink is both simpler and truly global.

The chosen level is persisted to a small JSON state file
(``state/system.json``) and re-applied at boot via :meth:`VolumeController.apply`,
so loudness is deterministic regardless of what PipeWire remembers between runs.

Every OS mutation is a no-op under the simulator (``-s``) so a dev machine's
audio is never touched -- consistent with the rest of the hardware-gated code.
"""
import json
import os
import subprocess
import sys

from .config import config


class VolumeController:
    """Load/persist a master volume level and push it to the OS default sink.

    Steps clamp to ``[config.Volume.MIN, config.Volume.MAX]`` in
    ``config.Volume.STEP`` increments. Each step applies to the OS sink and (when
    the level actually changed) persists to the state file.

    Args:
        simulated: If True, OS calls are skipped (the level is still loaded,
            stepped, and persisted). Defaults to detecting the ``-s`` CLI flag,
            so the simulator and headless tests never touch real audio.
    """

    SINK = "@DEFAULT_AUDIO_SINK@"

    def __init__(self, simulated=None):
        cfg = config.Volume
        self.min = cfg.MIN
        self.max = cfg.MAX
        self.step = cfg.STEP
        self.simulated = ("-s" in sys.argv) if simulated is None else simulated
        self.path = (cfg.STATE_PATH if os.path.isabs(cfg.STATE_PATH)
                     else os.path.join(config.PROJECT_ROOT, cfg.STATE_PATH))
        self.level = self._load(cfg.DEFAULT)

    # -- persistence --------------------------------------------------------
    def _load(self, default):
        """Read the saved level, falling back to ``default`` if absent/corrupt."""
        level = default
        try:
            with open(self.path) as f:
                level = float(json.load(f).get("volume", default))
        except (OSError, ValueError, TypeError):
            pass
        return self._clamp(level)

    def _save(self):
        """Persist the current level, preserving any other keys in the file."""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            try:
                with open(self.path) as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        data = {}
            except (OSError, ValueError, TypeError):
                data = {}
            data["volume"] = self.level
            with open(self.path, "w") as f:
                json.dump(data, f)
        except OSError as e:
            print(f"[Volume] could not save level: {e}")

    # -- level math ---------------------------------------------------------
    def _clamp(self, value):
        return max(self.min, min(self.max, round(value, 4)))

    def peek_down(self):
        """The level one step down, clamped, without changing anything."""
        return self._clamp(self.level - self.step)

    @property
    def percent(self):
        """Current level as an integer 0..100."""
        return int(round(self.level * 100))

    @property
    def fraction(self):
        """Current level as a 0..1 float (alias for ``level``)."""
        return self.level

    @property
    def is_max(self):
        return self.level >= self.max

    @property
    def is_muted(self):
        return self.level <= self.min

    # -- actions ------------------------------------------------------------
    def apply(self):
        """Push the current level to the OS default sink (no-op under ``-s``)."""
        if self.simulated:
            print(f"[Volume] (sim) OS volume -> {self.percent}%")
            return
        try:
            subprocess.run(
                ["wpctl", "set-volume", self.SINK, f"{self.level}"],
                check=False,
            )
        except Exception as e:
            print(f"[Volume] wpctl set-volume failed: {e}")

    def step_up(self, apply_os=True):
        """Raise volume one step, apply to the OS, and persist. Returns the level."""
        return self._step(+self.step, apply_os)

    def step_down(self, apply_os=True):
        """Lower volume one step, persist, and (unless ``apply_os`` is False) apply.

        ``apply_os=False`` lets a caller record/show the new (lower) level now but
        defer the actual OS change -- used when stepping to mute, so a spoken
        confirmation can still be heard at the old, audible level before the sink
        is silenced.
        """
        return self._step(-self.step, apply_os)

    def _step(self, delta, apply_os):
        new = self._clamp(self.level + delta)
        changed = new != self.level
        self.level = new
        if apply_os:
            self.apply()
        if changed:
            self._save()
        return self.level
