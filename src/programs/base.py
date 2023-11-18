"""
base.py

All programs should subclasss Program, and be put in this (program) directory.
"""
__all__ = ['State', 'StateSequence', 'StateMachine', 'Program']
from .. import config
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
  PROGRAMS = { }

  def __init__(self, game): #input_manager: InputManager):
    self.preload_all_programs()
    self.game = game
    self.input_manager = game.input_manager
    self.state = State(0x00)
  
  @classmethod
  def register_program(cls, program):
      """
      Called when Program subclass is instantiated (as a singleton,
      right after definition) in it's base class __init__ function.)
      """
      cls.PROGRAMS[program.__class__.__name__] = program
      print('registered', program.__class__.__name__)

  def swap_program(self, program_name):
    """
    change the active program, and give it references
    to input_manager and game objects.
    """
    self.program = self.PROGRAMS[program_name]
    self.program.game = self.game
    self.program.input_manager = self.input_manager
    if config.DEBUG:
        print('loaded program: ', program_name)
    
  def update(self, dt):
    # TODO: process any system wide input?
    self.program.update(dt)
    
##-- END STATE MACHINE --##
##-----------------------##

##########################
### PROGRAM base class ###
#                        #

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
        StateMachine.register_program(self) 

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

