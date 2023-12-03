"""
base.py

All programs should subclasss Program, and be put in this (program) directory.
"""

__all__ = ['State', 'StateSequence', 'StateMachine', 'Program']

import time
from heapq import heappush, heappop
from ..config import config
from ..animation import hold_pattern

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
    self.buttons = int(word) & (2**14-1)
    self.toggles = (int(word) & (3 << 14)) >> 14
    self.word = int(word)
    
  def get_on(self):
    return [i for i in range(16) if ((self.word & (1 << i)) >> i)]

  def get_buttons_on(self):
    return [i for i in range(14) if ((self.buttons & (1 << i)) >> i)]

  def get_toggles_on(self):
    return [i for i in range(2) if ((self.toggles & (1 << i)) >> i)]

  def to_list(self):
    state_list = [0]*16
    for bit_index in range(16):
      value = (self.word & (1 << bit_index)) >> bit_index
      state_list[bit_index] = value
    return state_list

  @classmethod
  def from_list(cls, buttons, toggles=(0,0)):
    # convert list of integer indices to 16 bit words
    word = 0x00
    for bit_index in buttons:
      word |= (1 << bit_index)
    word |= (toggles[0] << 14)
    word |= (toggles[1] << 15)
    return cls(word)

  def __int__(self):
    return self.word 

  def __or__(self, other):
    if isinstance(other, State):
      other = other.word
    return State(self.word | other)

  def __xor__(self, other):
    if isinstance(other, State):
      other = other.word
    return State(self.word ^ other)

  def __and__(self, other):
    if isinstance(other, State):
      other = other.word
    return State(self.word & other)

  def __lshift__(self, other):
    return State(self.word << int(other))

  def __rshift__(self, other):
    return State(self.word >> int(other))

  def __eq__(self, other):
    return self.word == int(other)

  def __repr__(self):
      s = f'State(buttons={self.get_buttons_on()}, '
      s += f'toggles={self.get_toggles_on()})'
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
  PAUSED = { }

  def __init__(self, game): #input_manager: InputManager):
    self.game = game
    self.composer = BirthdayComposer(game)
    self.input_manager = game.input_manager
    self.state = State(0x00)
    self.program = None

  @classmethod
  def register_program(cls, program):
      """
      Called when Program subclass is instantiated (as a singleton,
      right after definition) in it's base class __init__ function.)
      """
      cls.PROGRAMS[program.__class__.__name__] = program
      print('registered', program.__class__.__name__)

  def launch_single_program(self, program_name: str):
    """
    Program invoked with command line option "-p [Program Name]"
    """
    self.program = self.PROGRAMS[program_name]
    self.program.make_active_program(self.game)
    self.program.start()
    if config.DEBUG:
        print('loaded program: ', self.__class__.__name__)

  def start_composition(self):
    self.composer.start()
    self.swap_program()

  def launch_program(self, name):

        self.start()
        if config.DEBUG:
            print('loaded program: ', self.__class__.__name__)

  def swap_program(self, pause=False):
    """
    change the active program, and give it references
    to input_manager and game objects. Uses Composer
    instance to advance through pre-defined program sequence.
    """
    # pause or quit current program, unless this is the first program
    if pause and self.program:
      # note: 'pause' is not currently being used
      self.PAUSED[self.program.__class__.__name__] = self.program
      self.program.pause()
    else:
      pass
      #self.program.finish()

    # load next program
    self.composer.next_program()
    self.program = self.PROGRAMS[self.composer.program_name]
    self.program.make_active_program(self.game)
    self.program.start(**self.composer.program_kwargs)
    
  def update(self, dt):
    # TODO: process any system wide input?
    # update currently running program
    self.program.update(dt)

##-- END STATE MACHINE --##
##-----------------------##

##########################
### PROGRAM base class ###
#                        #

class Composer:
  """
  Basically a show-runner, keeps a record of a sequence of events/
  programs to be run, and the transitions that trigger swapping
  to occur.
  """
  def __init__(self, game): 
    self.game = game
    self.program_index = -1
    self.program_name_sequence = None # subclass must populate this in self.load_script
    self.load_script()

  def load_script(self):
    """
    Override in subclass
    """ 
    raise NotImplementedError('Subclass this method!')

  def start(self):
    """
    State machine will call this once; if any
    runtime initialization is needed, it can go here.
    """
    print('composer started')

  def finish(self):
    print('Composer script is complete.')
    return None

  @property
  def program_name(self):
    return self.program_name_sequence[self.program_index]

  @property
  def program_kwargs(self):
    return self.program_kwargs_sequence[self.program_index]
  
  def next_program(self):
    self.program_index += 1

    if self.program_index == len(self.program_name_sequence):
      return self.finish()

    return True

class BirthdayComposer(Composer):
  def load_script(self):
    # todo: put this data in one array [(name, args), ...]
    # and have class @properties fixed to match
    self.program_name_sequence = ['ClueFinder', 'TogglePattern', 'Flipper', 'TogglePattern', 'Golf', 'TogglePattern']
    self.program_kwargs_sequence = [
            dict(),
            dict(start_audio='nathan_clue_one.wav', toggle_pattern=[3,0,3],
                  hold_animation=hold_pattern(pattern=config.LASER_HOLD_PATTERN)),
            dict(),
            dict(start_audio='neo_morpheus_clue_two.wav', toggle_pattern=[1,2,0]),
            dict(),
            dict(start_audio='nathan_clue_final.wav', toggle_pattern=[0,1,2]), # unused toggle pattern for now
    ]

class Program:
    """
    Subclass this with triggers mapping filled,
    and default_action, process_input overridden.
    input_manager will be set by StateMachine.
    """
    schedule_id = 0
    scheduler = [] # heap
  
    cooldowns = { } # button id => deadline_tick

    system_triggers = { } # TODO .. enter SystemSettings, enter GameSelect modes
    triggers = { }

    def __init__(self):
        self.MODE_SWITCH_SEQ = StateSequence([
                                    State.from_list(buttons=[6], toggles=(1,1)),
                                    State.from_list(buttons=[6], toggles=(0,0)),
                                    State.from_list(buttons=[6], toggles=(1,1))],
                                    maxlen=6)
        StateMachine.register_program(self) 
        self._tick = 0

    @property
    def tick(self):
      """
      Read-only so that subclass doesn't erroneously
      update tick. Increments once per frame.
      """
      return self._tick
    
    def update(self, dt):
        """
        Called once per frame. Subclass in user program.
        """
        #TODO process system_triggers here (subclass should call super())
        self.check_cooldowns()
        self.check_schedule()
        if self.input_manager.changed_state:
            pass
            #state = input_manager.state
            #action = self.triggers.get(state, self.default_action)
            #action(state)
        self._tick += 1

    def start(self):
      """
      Called the first time program is loaded.
      """
      return RuntimeError('override this method in subclass')

    def quit(self, next_program=None):
      print('Program base class quit method called.')
      self.game.state_machine.swap_program()

    def make_active_program(self, game):
        self.game = game
        self.input_manager = self.game.input_manager
#        self.start()
#        if config.DEBUG:
#            print('loaded program: ', self.__class__.__name__)

    def after(self, ms, func, *args, **kwargs):
        deadline = time.time() + ms/1000
        f = lambda: func(*args, **kwargs)
        heappush(self.scheduler, (deadline, self.schedule_id, f))
        self.schedule_id += 1

    def check_schedule(self):
        if self.scheduler:
            now = time.time()
            while self.scheduler:
                nearest_deadline, sched_id, func = heappop(self.scheduler)
                if now - nearest_deadline > 0:
                    # deadline has past, call func
                    print('calling scheduled func with id #', sched_id)
                    func()
                else:
                    # no func is ready to be called
                    heappush(self.scheduler, (nearest_deadline, sched_id, func))
                    break

    def start_cooldown(self, button_id, ms=250):
        cooldown_ticks = int(config.FPS*ms/1000) # quarter-second cooldown after button press is default
        deadline_tick = cooldown_ticks + self.tick
        self.cooldowns[button_id] = deadline_tick

    def check_cooldowns(self):
        to_free = []
        for button_id, deadline_tick in self.cooldowns.items():
            if self.tick - deadline_tick > 0:
                to_free.append(button_id)
        for button_id in to_free:
            self.cooldowns.pop(button_id)

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

