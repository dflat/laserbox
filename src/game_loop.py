"""The game loop: clock, laser output model, and the top-level :class:`Game`.

:class:`Game` wires the subsystems together and runs the fixed-timestep loop:
poll input -> advance animations -> update the active program -> push the laser
word to the output register. :class:`GameClock` paces the loop to a target FPS.
:class:`LaserBay` is the laser-output model programs write to (collapsed into a
single 16-bit word each frame). On the desktop this class is subclassed by
:class:`~src.simulator.simulator.Simulator`.
"""
import sys
import time
from collections import deque, namedtuple
import pygame
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
  """Fixed-timestep clock that paces the loop to ``FPS`` frames per second.

  Tracks a target "playhead" (frame * target_dt) versus the actual elapsed
  time and sleeps to absorb the difference, so frames don't drift fast.

  Args:
      FPS: Target frames per second.
  """
  def __init__(self, FPS):
    self.FPS = FPS
    self.target_dt = 1/FPS
    self.t0 = time.time()
    self.t = self.t0
    self.prev_t = self.t0
    self.frame = 0
    self.target_playhead = 0
    self.actual_playhead = 0
    self.dt_history = deque(maxlen=60*10)

  def tick(self, fps):
    """Sleep to hold the target frame rate; return the frame's dt in ms."""
    self.t = time.time()
    self.target_playhead = self.frame * self.target_dt
    self.actual_playhead = self.t - self.t0
    wait = self.target_playhead - self.actual_playhead
    if wait > 0:
      #print('waiting ms:', wait*1000)
      time.sleep(wait)

    dt = self.t - self.prev_t
    #print('dt ms:', dt*1000)
    self.dt_history.append(dt)
    self.prev_t = self.t
    self.frame += 1
    return dt*1000

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
    """Run the main loop until KeyboardInterrupt (or an error)."""
    self._running = True
    self.t_game_start = time.time()
    self.clock = GameClock(self.FPS)
    dts = []
    dt = 1000/self.FPS
    try:
        while True:
          self.update(dt)
          self.render()
          dt = self.clock.tick(self.FPS)
          dts.append(dt)
    except KeyboardInterrupt:
        print('goodbye.')
        print('avg dt:', sum(dts)/len(dts))
        self.quit()
    except Exception as e:
        self.cleanup()
        raise RuntimeError('crashed...') from e
    #finally:
    #    self.quit()

  def cleanup(self):
    """Release GPIO resources."""
    self._running = False
    GPIO.cleanup()
    print('cleaned up.')

  def quit(self):
    """Clean up, shut down pygame, and exit the process."""
    self.cleanup()
    pygame.quit()
    print('quitting.')
    sys.exit()

if __name__ == "__main__":
    g = Game()
    g.run()
