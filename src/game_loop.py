import sys
import time
from collections import deque, namedtuple
import pygame
from .audio_utils import Mixer
from .shift_register import InputShiftRegister, OutputShiftRegister
from . import config
from .programs import State, StateSequence, StateMachine
from .event_loop import *
from . import config
if sys.platform == 'linux':
  import RPi.GPIO as GPIO

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
      time.sleep(wait)
    
    dt = self.t - self.prev_t
    self.dt_history.append(dt)
    self.prev_t = self.t
    self.frame += 1
    return dt
  
class InputManager:
  HISTORY_SIZE = 100
  
  def __init__(self, register: 'InputShiftRegister'):
    self.register = register
    self.history = deque(maxlen=self.HISTORY_SIZE)
    self.state = State(0)
    self.prev_state = State(0)
    self.changed_state = False
    
  def poll(self):
    self.state = State(self.register.read_word())
    if self.state == self.prev_state:
      self.changed_state = False
      return

    # state has changed, process new input...
    self.changed_state = True
    self.history.append(self.state)
    self.generate_events()

    # process system wide triggers...TODO
    # process program specific triggers...TODO

    self.prev_state = self.state

  def generate_events(self):
      """
      Check for and categorize input-generated events.
      """
      events.put(StateChangeEvent(state=self.state))  # todo: should this event be an event ?

      self.diff = self.prev_state ^ self.state       # bits that changed 
      self.flipped_on = self.diff & self.state       # changed and is currently on (= just flipped on)
      self.flipped_off = self.diff & self.prev_state # changed and was previously on (= just flipped off)

      if config.DEBUG:
          pass
          #print('FLIPPED ON:', self.flipped_on)
          #print('FLIPPED OFF:', self.flipped_off)

      for button_id in self.flipped_on.get_buttons_on():
          events.put(ButtonDownEvent(key=button_id))

      for toggle_id in self.flipped_on.get_toggles_on():
          events.put(ToggleOnEvent(key=toggle_id))

      for button_id in self.flipped_off.get_buttons_on():
          events.put(ButtonUpEvent(key=button_id))

      for toggle_id in self.flipped_off.get_toggles_on():
          events.put(ToggleOffEvent(key=toggle_id))

    
  def get_history_sequence(self, n):
      return StateSequence(self.history[-n:])

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

class OutputManager:
  def __init__(self, register: 'OutputShiftRegister'):
    self.register = register
    self.laser_mask = 2**14 - 1 # first 14 bits for laser state
    self.extra_mask = 3 << 14 # last 2 bits for extra state
    self.word = 0x00
    self.prev_word = None
    self.register.push_word(0)

  def set_bit(self, index, value): # maybe defunct
    if value:
      self.word |= (1 << index)
    else:
      self.word &= ~(1 << index)

  def set_word(self, word): # maybe defunct
    self.word = word

  def push_word(self, word):
    """
    Push word, unless it is identical to the last pushed word.
    """
    if word == self.prev_word:
      return
    self.register.push_word(word)
    self.prev_word = word
  

class Animation:
  def __init__(self, dur, loops=0, done_callback=None):
    self.dur = dur
    self.loops = loops
    self.done_callback = done_callback


class Game:
  def __init__(self, PISOreg, SIPOreg, mixer, events):
    self.FPS = config.FPS
    self.input_manager = InputManager(register=PISOreg)
    self.outputs = OutputManager(register=SIPOreg)
    self.lasers = LaserBay(14) # users interact with this to drive laser output
    self.mixer = mixer
    self.events = events # event loop reference (redundant as it is global singleton imported in this module)
    self.state_machine = StateMachine(self)
    self.state_machine.swap_program(config.START_PROGRAM)
    
  def update(self, dt):
    # read input
    self.input_manager.poll()
    changed_state = self.input_manager.changed_state

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
    dt = 1/self.FPS
    try:
        while True:
          self.update(dt) 
          self.render()
          dt = self.clock.tick(self.FPS)
    except:
        self.quit()
    self.quit()
    
  def quit(self):
    self._running = False
    pygame.quit()
    GPIO.cleanup()
    sys.exit()

if __name__ == "__main__":
    g = Game()
    g.run()
