import time
import pygame
from collections import deque, namedtuple
from .audio_utils import Mixer
from .shift_register import InputShiftRegister, OutputShiftRegister
from .shift_register import DummyInputShiftRegister, DummyOutputShiftRegister
from . import config
from .programs import StateSequence, StateMachine

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
    
  def tick(self):
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
    self.button_mask = 2**14 - 1 # first 14 bits for button state
    self.toggler_mask = 3 << 14 # last 2 bits for toggle switch state
    self.history = deque(maxlen=self.HISTORY_SIZE)
    self.state = 0x00
    self.prev_state = 0x00
    self.button_state = 0x00
    self.toggler_state = 0x00
    self.changed_state = False
    
  def poll(self):
    self.state = self.register.read_word()
    if self.state == self.prev_state:
      self.changed_state = False
      return
    # state has changed, process new input...
    self.changed_state = True
    self.history.append(self.state)
    self.button_state = self.state & self.button_mask
    self.toggler_state = (self.state & self.toggler_mask) >> 14

    # process system wide triggers...TODO
    #print('new state:', 'buttons: ',self.button_state, 'toggles: ',self.toggler_state)
    # process program specific triggers...TODO
    
    self.prev_state = self.state
    
  def get_history_sequence(self, n):
      return StateSequence(self.history[-n:])

class OutputManager:
  def __init__(self, register: 'OutputShiftRegister'):
    self.register = register
    self.laser_mask = 2**14 - 1 # first 14 bits for laser state
    self.extra_mask = 3 << 14 # last 2 bits for extra state
    self.word = 0x00

  def set_bit(self, index, value):
    if value:
      self.word |= (1 << index)
    else:
      self.word &= ~(1 << index)

  def set_word(self, word):
    self.word = word
  

class Animation:
  def __init__(self, dur, loops=0, done_callback=None):
    self.dur = dur
    self.loops = loops
    self.done_callback = done_callback


class Game:
  def __init__(self, FPS=30):
    self.FPS = FPS
    PISOreg = DummyInputShiftRegister()  # Parallel In, Serial Out register
    self.input_manager = InputManager(register=PISOreg)
    SIPOreg = DummyOutputShiftRegister()       # Serial In, Parallel Out register
    self.outputs = OutputManager(register=SIPOreg)
    self.state_machine = StateMachine(self)
    
  def update(self, dt):
    self.input_manager.poll()
    changed_state = self.input_manager.changed_state
    self.state_machine.update(dt)
        
  def run(self):
    print(self.state_machine.PROGRAMS)
    self.state_machine.swap_program('ClueFinder')
    self.m = Mixer()
    self.t_game_start = time.time()
    self.clock = GameClock(self.FPS)
    dt = 1/self.FPS
    while True:
      self.update(dt) 
       
      dt = self.clock.tick()
    

if __name__ == "__main__":
    g = Game()
    g.run()
