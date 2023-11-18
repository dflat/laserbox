import time
import pygame
from collections import deque, namedtuple
#from .event_loop import EventLoop, Event, EventType
from .audio_utils import Mixer
from .shift_register import InputShiftRegister, OutputShiftRegister
from .shift_register import DummyInputShiftRegister, DummyOutputShiftRegister
#from programs import *

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


###########################
###    STATE MACHINE    ###
#                         #

class State:
  """
  Conveinence object to create a 2-byte word
  from either a list [use State.from_list] of
  integers corresponding to bit-positions that
  are 'on'; or, simply initialize with a 16-bit integer.
  """
  def __init__(self, word:int):
    self.buttons = word & (2**14-1)
    self.toggles = (word & (3 << 14)) >> 14
    self.word = word
    
  def __int__(self):
    return self.word 

  @classmethod
  def from_list(cls, buttons, toggles=(0,0)):
    # convert list of integer indices to 16 bit words
    word = 0x00
    for bit_index in buttons:
      word |= (1 << bit_index)
    word |= (toggles[0] << 14)
    word |= (toggles[1] << 15)
    return cls(word)

  def __repr__(self):
      s = f'State<buttons={bin(self.buttons)[2:].zfill(16)}, '
      s += f'toggles={bin(self.toggles)[2:].zfill(2)}>'
      return s
    
class StateSequence:
  """
  Collection object that holds a sequence of State objects.
  Also holds a pure integer copy of the sequence as ::word_sequence::
  Has a ::match:: method, which is used to compare two sequences.

  Args:
    use a ::maxlen:: greater than the length of ::sequence::
    to allow for comparison "leniency" (see match method).
  """
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
      
class StateMachine:
  
  def __init__(self, input_manager: InputManager):
    self.PROGRAM_MAP = programs # { triggering state => program }
    self.input_manager = input_manager
    self.state = State(0x00)
  
  def swap_program(self, program_name):
    self.program = self.PROGRAM_MAP[program_name]
    self.program.input_manager = self.input_manager
    print('loaded program: ', program_name)
    
  def update(self, dt):
    # TODO: process any system wide input?
    self.program.update(dt)
    
##-- END STATE MACHINE --##
##-----------------------##

########################
### PROGRAMS / MODES ###
#                      #

class Program:
    """
    Subclass this with triggers mapping filled,
    and default_action, process_input overridden.
    input_manager will be set by StateMachine.
    """
  
    system_triggers = { } # TODO .. enter SystemSettings, enter GameSelect modes
    triggers = { }

    def __init__(self):
        self.MODE_SWITCH_SEQ = StateSequence([
                                    State.from_list(buttons=[6], toggles=(1,1)),
                                    State.from_list(buttons=[6], toggles=(0,0)),
                                    State.from_list(buttons=[6], toggles=(1,1))],
                                    maxlen=6)

    def update(self, dt):
        """
        Called once per frame. Subclass in user program.
        """
        #TODO process system_triggers here (subclass should call super())
        if self.input_manager.changed_state:
            pass
            #state = input_manager.state
            #action = self.triggers.get(state, self.default_action)
            #action(state)

    def match_triggers(self, state):
        # match any single-state trigger
        action = self.triggers.get(state, self.default_action)
        return action

    def match_sequence_triggers(self, maxlen):
        # match any sequence-of-states trigger
        seq = self.input_manager.get_history_sequence(n=maxlen)
        for trig_seq, action in self.sequence_triggers.items():
            if trig_seq.match(seq):
                return action
        return self.no_action
        

    def default_action(self, state: 'State'):
        raise RuntimeError('default_action needs to be implemented in Program subclass.')

    def no_action(self, state: 'State'):
        return None

class SystemSettings(Program):
    pass

class GameSelect(Program):
    pass

class ClueFinder(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }

    def button_pressed(self, word):
        print('clue finder got:', word, int(word))

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        if self.input_manager.changed_state:
            state = State(self.input_manager.state)
            action = self.match_triggers(state)
            action(state)
        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

    def default_action(self, state: 'State'):
        self.button_presssed(state)

class Trivia(Program):
  pass


programs = {ClueFinder.__name__: ClueFinder(),
            Trivia.__name__: Trivia()
}
#--                      --#
#-- END PROGRAMS / MODES --#

class Game:
  def __init__(self, FPS=30):
    self.FPS = FPS
    PISOreg = DummyInputShiftRegister()  # Parallel In, Serial Out register
    self.inputs = InputManager(register=PISOreg)
    SIPOreg = DummyOutputShiftRegister()       # Serial In, Parallel Out register
    self.outputs = OutputManager(register=SIPOreg)
    self.state_machine = StateMachine(self.inputs)
    
  def update(self, dt):
    self.inputs.poll()
    changed_state = self.inputs.changed_state
    self.state_machine.update(dt)
        
  def run(self):
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
