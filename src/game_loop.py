import time
import pygame
from collections import deque, namedtuple
#from event_loop import EventLoop, Event, EventType
from audio_utils import Mixer
from shift_register import InputShiftRegister, OutputShiftRegister

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
    self.history = deque(maxlen=HISTORY_SIZE)
    self.prev_state = 0x00
    self.button_state = 0x00
    self.toggler_state = 0x00
    self.changed_state = False
    
  def poll(self):
    state = self.register.read_word()
    if state == self.prev_state:
      self.changed_state = False
      return
    # state has changed, process new input...
    self.changed_state = True
    self.history.append(state)
    self.button_state = state & self.button_mask
    self.toggler_state = (state & self.toggler_mask) >> 14
    
    self.prev_state = state

class OutputManager:
  def __init__(self, register: 'ShiftRegister'):
    self.register = register
    self.laser_mask = 2**14 - 1 # first 14 bits for laser state
    self.extra_mask = 3 << 14 # last 2 bits for extra state

### PROGRAMS / MODES ###
###                  ###

class State:
  def __init__(self, toggle, buttons):
    self.toggle = toggle
    self.buttons = buttons
    self.word = int(self)
    
  @property
  def buttons(self):
    return self._buttons 
  @buttons.setter
  def buttons(self, button_list):
    if isinstance(button_list, int):
      self._buttons = button_list
      return
    # convert list of integer indices to 16 bit words
    button_word = 0x00
    for bit_index in button_list:
      button_word |= (1 << bit_index)
    self._buttons = button_word

  def __int__(self):
    return self.buttons | (self.toggle << 14)
    
class StateSequence():
  def __init__(self, sequence: 'list(State) or list(int)', maxlen=None):
    self.sequence = sequence
    self.word_sequence = self.as_words()
    self.maxlen = maxlen or len(sequence)
  
  def as_words(self):
    return [int(s) for s in self.sequence]  
  
  def __getitem__(self, index): return self.word_sequence[index]
  def __iter__(self): return iter(self.word_sequence)
  def __len__(self): return len(self.word_sequence)
  def __getattr__(self, attr): return getattr(self.word_sequence, attr)
      
  def match(self, other_sequence):
    """
    Compares internal ::self.sequence:: with test ::other_sequence::
      over ::self.maxlen:: successive items. If maxlen > len(self.sequence)
      there is "leniency" in the sequence check, meaning successive words must occur
      in order, but not necessary directly adjacent to one another.
      
      E.g: other_sequence = [A, x, B, y, C]
           self.sequence = [A, B, C]
           
           (maxlen >= 5) yields a match, (maxlen < 5) will not match.        
    """
    match_index = 0
    for i in range(min(len(other_sequence), self.maxlen)):
      target_word = int(self.sequence[match_index])
      test_word = int(other_sequence[i])
      if test_word == target_word:
        match_index += 1
      if match_index == len(self.sequence):
        return True
    return False
      
           
class Program:
  MODE_SWITCH_SEQ = StateSequence([ State(toggle=3, buttons=[6]),
                                    State(toggle=0, buttons=[6]),
                                    State(toggle=3, buttons=[6]) ], maxlen=6)
                                    
  """ subclass to implement a program/mode for the box
  """
  def __init__(self):
    pass
  def update(self, state):
    pass
  def run(self):
    pass
    
class ClueFinder(Program):
  pass
  
class Trivia(Program):
  pass

programs = {0: ClueFinder(),
            1: Trivia()
}

#--                      --#
#-- END PROGRAMS / MODES --#

class StateMachine:
  PROGRAM_MAP = programs # { triggering state => program }
  
  def __init__(self, inputs):
    self.inputs = inputs
    self.state = 0x00
  
  def swap_program(self, state):
    self.program = self.PROGRAM_MAP[state]
    
  def advance(self):
    pass
    
class Game:
  def __init__(self, FPS=30):
    self.FPS = FPS
    PISOreg = DummyInputShiftRegister()  # Parallel In, Serial Out register
    self.inputs = InputManager(register=PISOreg)
    SIPOreg = ShiftRegister()       # Serial In, Parallel Out register
    self.outputs = OutputManager(register=SIPOreg)
    self.state_machine = StateMachine(self.inputs)
    self.t_game_start = time.time()
    self.run()
    
  def update(self, dt):
    self.inputs.poll()
    if self.inputs.changed_state:
      self.state_machine.advance()
    
        
  def run(self):
    self.clock = GameClock(self.FPS)
    dt = 1/FPS
    while True:
      self.update(dt) 
       
      dt = self.clock.tick()
    

if __name__ == "__main__":
    g = Game()
    g.run()
