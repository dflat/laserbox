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
if sys.platform == 'linux':
  import RPi.GPIO as GPIO

if '-p' in sys.argv:
    config.START_PROGRAM = sys.argv[2]

class GameClock:
  def __init__(self, FPS):
    self.FPS = FPS
    self.target_dt = 1/FPS
    self.t0 = time.time()
    self.t = self.t0
    self.prev_t = self.t0
    self.frame = 1
    self.target_playhead = 0
    self.actual_playhead = 0
    self.dt_history = deque(maxlen=60*10)
    
  def tick(self, fps):
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
  """
  Should only be accessed through LaserBay
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
  """
  User interacts with this object, which in turn controls
  the state of an array of LaserPort objects.

  Keeps a cache of last state via a 'self.clean' flag.
  """
  def __init__(self, n=14):
    self.n = n
    self.lasers = [LaserPort(i) for i in range(self.n)]
    self.word = 0
    self.clean = True

  def turn_on(self, laser_id):
    """ conveinence method """
    self.set_value(laser_id, 1)

  def turn_off(self, laser_id):
    """ conveinence method """
    self.set_value(laser_id, 0)

  def set_value(self, laser_id, value):
    """
    Set a given laser on or off by it's id.
    """
    self.clean = False
    if value == 1:
      self.lasers[laser_id]._turn_on()
    elif value == 0:
      self.lasers[laser_id]._turn_off()

  def set_word(self, word):
    """
    Set entire word directly, rather than through individual
    laser manipulation.
    """
    self.word = word
    self.clean = True

  def to_word(self):
    """
    If state hasn't changed since to_word was last called
    (as indicated by self.clean) returns the cached word.
    """
    if self.clean:
      return self.word
    self.word = sum(self.lasers[i].on << i for i in range(self.n))
    self.clean = True
    return self.word

class Game:
  def __init__(self, PISOreg, SIPOreg, mixer, events):
    self.FPS = config.FPS
    self.input_manager = InputManager(register=PISOreg)
    self.outputs = OutputManager(register=SIPOreg)
    self.lasers = LaserBay(14) # users interact with this to drive laser output
    self.mixer = mixer
    self.events = events # event loop reference (redundant as it is global singleton imported in this module)
    Animation.game = self # hack to get game reference from animation instances (todo: make cleaner reference link)
    self.state_machine = StateMachine(self)
    self.state_machine.swap_program(config.START_PROGRAM)
    
  def update(self, dt):
    # read input
    self.input_manager.poll()
    changed_state = self.input_manager.changed_state

    # play any ongoing animations
    Animation.update_all(dt)

    # update currently running program
    self.state_machine.update(dt)

  def render(self):
    # push output
    laser_state_word = self.lasers.to_word()
    self.outputs.push_word(laser_state_word)

  def run(self):
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
    except Exception as e:
        print('raising unhandled exception in game.run:', e)
        raise
    finally:
        self.quit()
    
  def quit(self):
    self._running = False
    pygame.quit()
    GPIO.cleanup()
    print('cleaned up and quitting.')
    sys.exit()

if __name__ == "__main__":
    g = Game()
    g.run()
