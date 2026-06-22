"""Input/output managers that sit between the shift registers and the game.

:class:`InputManager` polls the input register each frame, diffs against the
previous read, and turns bit changes into events on the global event queue.
:class:`OutputManager` pushes the laser word to the output register, skipping
the write when the word is unchanged.
"""
from collections import deque
from .event_loop import *
from .programs import State, StateSequence
from .config import config

class InputManager:
  """Polls the input register and emits button/toggle events on change.

  Each :meth:`poll` reads a fresh :class:`~src.programs.base.State`, sets
  ``changed_state``, records history, and (on change) emits ButtonDown/Up and
  ToggleOn/Off events.

  Args:
      register: An object with a ``read_word()`` method (the real
          :class:`~src.shift_register.InputShiftRegister` or a dummy).
  """
  HISTORY_SIZE = 100

  def __init__(self, register: 'InputShiftRegister'):
    self.register = register
    self.history = deque(maxlen=self.HISTORY_SIZE)
    self.state = State(0)
    self.prev_state = State(0)
    self.changed_state = False

  def poll(self):
    """Read the register; if the state changed, record it and emit events."""
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
      """Diff against the previous state and emit one event per changed bit.

      Computes the bits that flipped on/off since the last poll and pushes a
      :class:`~src.event_loop.ButtonDownEvent` /
      :class:`~src.event_loop.ButtonUpEvent` /
      :class:`~src.event_loop.ToggleOnEvent` /
      :class:`~src.event_loop.ToggleOffEvent` for each, carrying the full state.
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
      """Return the last ``n`` states as a :class:`~src.programs.base.StateSequence`."""
      return StateSequence(self.history[-n:])


class OutputManager:
  """Pushes the laser word to the output register, de-duplicating writes.

  Args:
      register: An object with a ``push_word(word)`` method (the real
          :class:`~src.shift_register.OutputShiftRegister` or a dummy).
  """
  def __init__(self, register: 'OutputShiftRegister'):
    self.register = register
    self.laser_mask = 2**14 - 1 # first 14 bits for laser state
    self.extra_mask = 3 << 14 # last 2 bits for extra state
    self.word = 0x00
    self.prev_word = None
    self.register.push_word(0)

  def set_bit(self, index, value): # maybe defunct
    """Set or clear a single output bit on the cached word."""
    if value:
      self.word |= (1 << index)
    else:
      self.word &= ~(1 << index)

  def set_word(self, word): # maybe defunct
    """Replace the cached word wholesale."""
    self.word = word

  def push_word(self, word):
    """Push ``word`` to the register unless it equals the last pushed word."""
    if word == self.prev_word:
      return
    self.register.push_word(word)
    self.prev_word = word
