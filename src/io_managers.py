from collections import deque
from .event_loop import *
from .programs import State, StateSequence
from .config import config

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
      #events.put(StateChangeEvent(state=self.state))  # todo: should this event be an event ?

      self.diff = self.prev_state ^ self.state       # bits that changed 
      self.flipped_on = self.diff & self.state       # changed and is currently on (= just flipped on)
      self.flipped_off = self.diff & self.prev_state # changed and was previously on (= just flipped off)

      if config.DEBUG:
          pass
          #print('FLIPPED ON:', self.flipped_on)
          #print('FLIPPED OFF:', self.flipped_off)

      for button_id in self.flipped_on.get_buttons_on():
          events.put(ButtonDownEvent(key=button_id, state=self.state))

      for toggle_id in self.flipped_on.get_toggles_on():
          events.put(ToggleOnEvent(key=toggle_id, state=self.state))

      for button_id in self.flipped_off.get_buttons_on():
          events.put(ButtonUpEvent(key=button_id, state=self.state))

      for toggle_id in self.flipped_off.get_toggles_on():
          events.put(ToggleOffEvent(key=toggle_id, state=self.state))

    
  def get_history_sequence(self, n):
      return StateSequence(self.history[-n:])


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
  

