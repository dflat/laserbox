"""The game loop: clock, laser output model, and the top-level :class:`Game`.

:class:`Game` wires the subsystems together and runs the fixed-timestep loop:
poll input -> advance animations -> update the active program -> push the laser
word to the output register. :class:`GameClock` paces the loop to a target FPS.
:class:`LaserBay` is the laser-output model programs write to (collapsed into a
single 16-bit word each frame). On the desktop this class is subclassed by
:class:`~src.simulator.simulator.Simulator`.
"""
import sys
import signal
import pygame
from . import clock
from .audio_utils import Mixer
from .shift_register import InputShiftRegister, OutputShiftRegister
from .config import config
from .programs import State, StateSequence, StateMachine
from .event_loop import *
from .animation import Animation
from .io_managers import InputManager, OutputManager
if sys.platform == 'linux' and '-s' not in sys.argv:
  import RPi.GPIO as GPIO

if '-p' in sys.argv:
    config.START_PROGRAM = sys.argv[2]

class GameClock:
  """Fixed-timestep pacer that holds the loop at ``fps`` frames per second.

  Built on the monotonic :mod:`src.clock`, so it is immune to wall-clock / NTP /
  RTC adjustments (see that module for the bug this prevents). Each frame it
  sleeps until the next frame's scheduled time, then reports the real elapsed
  ``dt``.

  It is deliberately **not** a "make up lost time" clock. The previous design
  paced against an absolute playhead (``frame * target_dt`` vs elapsed); after
  any large gap -- a wall-clock leap, or a long stall -- it would stop sleeping
  and free-run for thousands of frames to catch the playhead up, compressing
  every frame-counted timeout. Here, if the loop falls more than
  ``MAX_FRAME_SKIP`` frames behind, the backlog is dropped and the schedule
  resyncs to *now*; the returned ``dt`` is clamped the same way, so a one-off
  hiccup can never inject a huge time step into game logic.

  Args:
      fps: Target frames per second.
  """
  MAX_FRAME_SKIP = 5  # frames of backlog tolerated before we resync instead of catching up

  def __init__(self, fps):
    self.fps = fps
    self.target_dt = 1.0 / fps
    self.max_lag = self.MAX_FRAME_SKIP * self.target_dt
    now = clock.monotonic()
    self.prev = now
    self.next_frame = now + self.target_dt

  def tick(self):
    """Sleep until the next frame is due; return the elapsed ``dt`` in ms."""
    now = clock.monotonic()
    wait = self.next_frame - now
    if wait > 0:
      clock.sleep(wait)
      now = clock.monotonic()

    # Real frame period, clamped so a stall can't spike dt for game logic.
    dt = now - self.prev
    if dt > self.max_lag:
      dt = self.target_dt
    self.prev = now

    # Schedule the next frame. If we've fallen too far behind (long stall or any
    # clock anomaly), drop the backlog and resync rather than free-run to catch up.
    self.next_frame += self.target_dt
    if self.next_frame < now - self.max_lag:
      self.next_frame = now + self.target_dt

    return dt * 1000.0

class LaserPort:
  """One laser's on/off state. Should only be accessed through :class:`LaserBay`.

  Args:
      id: The laser's index (0..13).
  """
  def __init__(self, id):
    self.id = id
    self.on = False
    self.brightness = 1 # not used for now, but possibly implement PWM brightness

  def _turn_on(self):
    self.on = True

  def _turn_off(self):
    self.on = False

class LaserBay:
  """The laser-output model programs write to.

  Holds an array of :class:`LaserPort` objects and collapses them into a single
  16-bit word for the output register. A ``clean`` flag caches the last word so
  :meth:`to_word` only recomputes when something changed.

  Args:
      n: Number of lasers (default 14).
  """
  def __init__(self, n=14):
    self.n = n
    self.lasers = [LaserPort(i) for i in range(self.n)]
    self.word = 0
    self.clean = True

  def turn_on(self, laser_id):
    """Convenience: turn a single laser on by id."""
    self.set_value(laser_id, 1)

  def turn_off(self, laser_id):
    """Convenience: turn a single laser off by id."""
    self.set_value(laser_id, 0)

  def set_value(self, laser_id, value):
    """Set a single laser on (1) or off (0) by its id."""
    self.clean = False
    if value == 1:
      self.lasers[laser_id]._turn_on()
    elif value == 0:
      self.lasers[laser_id]._turn_off()

  def set_word(self, word):
    """Set the entire laser word directly (bypasses per-laser objects)."""
    self.word = word
    self.clean = True

  def to_word(self):
    """Return the current 16-bit laser word, using the cache when unchanged."""
    if self.clean:
      return self.word
    self.word = sum(self.lasers[i].on << i for i in range(self.n))
    self.clean = True
    return self.word

class Game:
  """Top-level object: owns the subsystems and runs the main loop.

  Args:
      PISOreg: Input shift register (or dummy) with ``read_word()``.
      SIPOreg: Output shift register (or dummy) with ``push_word()``.
      mixer: A :class:`~src.audio_utils.Mixer`.
      events: The global event loop singleton.

  On construction it boots into GameSelect, unless launched with ``-p
  [Program]`` (which launches that single program directly).
  """
  def __init__(self, PISOreg, SIPOreg, mixer, events):
    self.FPS = config.FPS
    # Monotonic game-loop time in ms since the loop started: the sum of every
    # frame's real dt. The single timeline programs read (via ``self.now_ms``)
    # to set and check deadlines -- immune to wall-clock jumps by construction.
    self.now_ms = 0.0
    self.input_manager = InputManager(register=PISOreg)
    self.outputs = OutputManager(register=SIPOreg)
    self.lasers = LaserBay(14) # users interact with this to drive laser output
    self.mixer = mixer
    self.events = events # event loop reference (redundant as it is global singleton imported in this module)
    Animation.game = self # hack to get game reference from animation instances (todo: make cleaner reference link)
    self.state_machine = StateMachine(self)
    if '-p' in sys.argv:
      config.START_PROGRAM = sys.argv[2]
      self.state_machine.launch_single_program(config.START_PROGRAM)
    else:
      self.state_machine.enter_game_select()

  def update(self, dt):
    """One frame of logic: poll input, advance animations, update the program."""
    # advance the monotonic game-loop clock by this frame's elapsed time first,
    # so every deadline set or checked this frame sees a consistent ``now_ms``.
    self.now_ms += dt
    # read input
    self.input_manager.poll()
    changed_state = self.input_manager.changed_state

    # play any ongoing animations
    Animation.update_all(dt)

    # update currently running program
    self.state_machine.update(dt)

  def render(self):
    """Push the current laser word to the output register."""
    # push output
    laser_state_word = self.lasers.to_word()
    self.outputs.push_word(laser_state_word)

  def run(self):
    """Run the main loop until a stop signal, KeyboardInterrupt, or an error.

    A SIGTERM/SIGINT handler (installed here, *after* pygame is up so it wins
    over any handler SDL installed) flips ``_running`` so the loop exits
    promptly. That is what lets ``systemctl stop`` shut the box down in well
    under a second instead of waiting out systemd's kill timeout. Whatever the
    exit path, the ``finally`` clears the lasers and releases GPIO/pygame.
    """
    self._running = True
    self.t_game_start = clock.monotonic()
    self.clock = GameClock(self.FPS)
    self._install_signal_handlers()
    self.lasers.set_word(0)  # begin with every laser off
    self.render()
    dts = []
    dt = 1000/self.FPS
    try:
        while self._running:
          self.update(dt)
          self.render()
          dt = self.clock.tick()
          dts.append(dt)
    except KeyboardInterrupt:
        print('goodbye.')
    finally:
        if dts:
          print('avg dt:', sum(dts)/len(dts))
        self.cleanup()

  def _install_signal_handlers(self):
    """Stop the loop cleanly on SIGTERM/SIGINT (e.g. ``systemctl stop``).

    Installed from :meth:`run` (after pygame init) so it overrides any signal
    handler SDL set up -- otherwise SIGTERM is swallowed and shutdown stalls.
    """
    def _handle(signum, _frame):
        print(f'received signal {signum}; shutting down.')
        self._running = False
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle)

  def cleanup(self):
    """Turn off the lasers, silence audio, and release GPIO + pygame.

    Idempotent, and safe on both hardware and the simulator: GPIO is only
    touched when the real ``RPi.GPIO`` module was imported (Linux, no ``-s``).
    """
    if getattr(self, '_cleaned_up', False):
        return
    self._cleaned_up = True
    self._running = False
    try:
        self.outputs.push_word(0)  # physically clear all lasers
    except Exception as e:
        print('laser-off on shutdown failed:', e)
    try:
        self.mixer.stop_all()
    except Exception as e:
        print('audio stop on shutdown failed:', e)
    if sys.platform == 'linux' and '-s' not in sys.argv:
        GPIO.cleanup()
    pygame.quit()
    print('clean shutdown complete.')

  def quit(self):
    """Clean up and exit the process (hard exit for external callers)."""
    self.cleanup()
    sys.exit()

if __name__ == "__main__":
    g = Game()
    g.run()
