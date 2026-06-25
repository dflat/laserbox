"""Program framework: states, the state machine, composers, and the Program base.

This module is the heart of laserbox's control flow. It defines:

* :class:`State` / :class:`StateSequence` -- value types wrapping the 16-bit
  input word (14 buttons + 2 toggles) and ordered sequences of them.
* :class:`GestureDetector` -- the non-consuming detector for the global
  GameSelect entry gesture.
* :class:`StateMachine` -- owns the active :class:`Program` and the current
  "context", and routes control between them.
* :class:`Composer` (and :class:`SingleEntryComposer`, :class:`BirthdayComposer`)
  -- a "context" is a Composer: an ordered script of programs to run.
* :class:`Program` -- the base class every mini-game subclasses.

To add a new game, subclass :class:`Program`, put it in this ``programs``
directory, and instantiate it once at import. See the "Authoring New Programs"
guide for the full walkthrough.
"""

__all__ = ['State', 'StateSequence', 'StateMachine', 'Program']

from heapq import heappush, heappop
from .. import clock
from ..config import config
from ..animation import hold_pattern, Animation
from ..event_loop import events

###########################
###    STATE MACHINE    ###
#                         #

class State:
  """A snapshot of the 16-bit input word.

  The low 14 bits are buttons; the top 2 bits are toggles. Construct from a raw
  16-bit integer, or from a list of "on" bit indices via :meth:`from_list`.
  Supports the bitwise operators (``|``, ``&``, ``^``, ``<<``, ``>>``) and
  compares equal to any object whose ``int()`` matches its word.

  Args:
      word: The raw 16-bit input word (anything convertible with ``int()``).

  Attributes:
      word (int): The full 16-bit value.
      buttons (int): The low 14 bits (button state).
      toggles (int): The top 2 bits, shifted down to 0..3 (toggle state).
  """
  def __init__(self, word:int):
    self.buttons = int(word) & (2**14-1)
    self.toggles = (int(word) & (3 << 14)) >> 14
    self.word = int(word)

  def get_on(self):
    """Return the indices (0..15) of every bit that is set."""
    return [i for i in range(16) if ((self.word & (1 << i)) >> i)]

  def get_buttons_on(self):
    """Return the indices (0..13) of buttons that are currently pressed."""
    return [i for i in range(14) if ((self.buttons & (1 << i)) >> i)]

  def get_toggles_on(self):
    """Return the indices (0..1) of toggles that are currently on."""
    return [i for i in range(2) if ((self.toggles & (1 << i)) >> i)]

  def to_list(self):
    """Return the word as a list of 16 bit values (index 0 = bit 0)."""
    state_list = [0]*16
    for bit_index in range(16):
      value = (self.word & (1 << bit_index)) >> bit_index
      state_list[bit_index] = value
    return state_list

  @classmethod
  def from_list(cls, buttons, toggles=(0,0)):
    """Build a State from button indices and toggle values.

    Args:
        buttons: Iterable of button indices (0..13) that should be on.
        toggles: ``(toggle0, toggle1)`` values (0 or 1 each). Defaults to off.

    Returns:
        State: The corresponding state.
    """
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
  """An ordered sequence of states with fuzzy, in-order matching.

  Holds the original ``sequence`` plus an integer copy in ``word_sequence``, and
  provides :meth:`match` for comparing against another sequence.

  Args:
      sequence: A list of :class:`State` (or int) values.
      maxlen: Comparison window. If greater than ``len(sequence)`` the match is
          "lenient": the target words must appear in order but need not be
          adjacent. Defaults to ``len(sequence)`` (strict, adjacent match).
  """
  def __init__(self, sequence: 'list(State) or list(int)', maxlen=None):
    self.sequence = sequence
    self.word_sequence = self.as_words()
    self.maxlen = maxlen or len(sequence)

  def as_words(self):
    """Return the sequence as a list of plain integers."""
    return [int(s) for s in self.sequence]

  def __getitem__(self, index): return self.word_sequence[index]
  def __iter__(self): return iter(self.word_sequence)
  def __len__(self): return len(self.word_sequence)
  def __getattr__(self, attr): return getattr(self.word_sequence, attr)

  def match(self, other_sequence):
    """Test whether this sequence occurs (in order) within ``other_sequence``.

    Compares ``self.sequence`` against ``other_sequence`` over up to
    ``self.maxlen`` items. With ``maxlen > len(self.sequence)`` there is
    leniency: the words must occur in order but need not be directly adjacent.

    Example:
        With ``self.sequence = [A, B, C]`` and
        ``other_sequence = [A, x, B, y, C]``: ``maxlen >= 5`` matches,
        ``maxlen < 5`` does not.

    Args:
        other_sequence: The sequence (of int/State) to test against.

    Returns:
        bool: True if a match is found within the window.
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

class GestureDetector:
  """Detector for the global GameSelect entry gesture.

  The gesture is: hold a set of "hold" buttons while a given toggle changes
  state a number of times (e.g. on->off->on). All hold buttons must remain
  pressed across every transition; releasing any one resets the detector.

  It is fed the latest :class:`State` whenever input changes. It is
  *non-consuming* -- it reads input state rather than pulling from the event
  queue -- so it works no matter how the active program handles its own input.
  Only the hold buttons and the chosen toggle matter; all other bits are
  ignored (masked).

  Args:
      hold_buttons: Iterable of button indices that must be held.
      toggle_index: Which toggle (0 or 1) must change state.
      transitions: Number of toggle state-changes required to fire.
  """
  def __init__(self, hold_buttons, toggle_index, transitions):
    self.hold_buttons = list(hold_buttons)
    self.toggle_index = toggle_index
    self.required = transitions
    self.reset()

  def reset(self):
    """Clear progress (called on completion or when the hold is broken)."""
    self.count = 0
    self.last_toggle = None

  def _holding(self, state):
    on = set(state.get_buttons_on())
    return all(b in on for b in self.hold_buttons)

  def _toggle_value(self, state):
    return (state.toggles >> self.toggle_index) & 1

  def feed(self, state):
    """Feed the latest state; return True on the change that completes it.

    Args:
        state: The current input :class:`State`.

    Returns:
        bool: True exactly on the transition that completes the gesture.
    """
    if not self._holding(state):
      self.reset()
      return False
    toggle = self._toggle_value(state)
    if self.last_toggle is None:
      # buttons just became held: establish the baseline toggle value
      self.last_toggle = toggle
      return False
    if toggle != self.last_toggle:
      self.count += 1
      self.last_toggle = toggle
    return self.count >= self.required


class StateMachine:
  """Owns the active program and routes control between programs/contexts.

  The box always has exactly one active :class:`Program`. A "context" (a
  :class:`Composer`) is an ordered script of programs; when the context is
  exhausted control returns to the GameSelect hub. The GameSelect program is
  the only thing that creates a new context.

  Each frame :meth:`update` first checks the global entry gesture (so GameSelect
  can be reached from any program), then ticks the active program.

  Class Attributes:
      PROGRAMS (dict): Program class name -> singleton instance (registered at
          import via :meth:`register_program`).
      COMPOSER_CLASSES (dict): Composer class name -> class (selectable from
          GameSelect, registered via :meth:`register_composer`).
  """
  PROGRAMS = { }          # name -> Program singleton (registered at import)
  COMPOSER_CLASSES = { }  # name -> Composer subclass (selectable from GameSelect)

  def __init__(self, game):
    self.game = game
    self.input_manager = game.input_manager
    self.state = State(0x00)
    self.program = None
    self.context = None  # current Composer-like context; None while in GameSelect
    self.gesture = GestureDetector(
        config.GameSelect.TRIGGER_BUTTONS,
        config.GameSelect.TRIGGER_TOGGLE,
        config.GameSelect.TRIGGER_TRANSITIONS,
    )

  @classmethod
  def register_composer(cls, composer_cls):
      """Class decorator: make a Composer subclass selectable by its name."""
      cls.COMPOSER_CLASSES[composer_cls.__name__] = composer_cls
      return composer_cls

  @classmethod
  def register_program(cls, program):
      """Register a Program singleton under its class name.

      Called from :meth:`Program.__init__`, so every program registers itself
      simply by being instantiated once at import time.
      """
      cls.PROGRAMS[program.__class__.__name__] = program
      print('registered', program.__class__.__name__)

  def _in_game_select(self):
    """True when the active program is the GameSelect hub."""
    return self.program is self.PROGRAMS.get('GameSelect')

  def _teardown_current_program(self):
    """Forcibly stop the active program's side effects.

    Ensures nothing leaks into the next program: clears the program's pending
    callbacks/cooldowns, stops all audio, kills running animations, and clears
    the lasers.
    """
    if self.program is None:
      return
    self.program.teardown()
    self.game.mixer.stop_all()
    Animation.kill_all()
    self.game.lasers.set_word(0)

  def _activate_program(self, name, **kwargs):
    """Tear down whatever is running, then start program ``name`` cleanly.

    Args:
        name: Program class name (key into :attr:`PROGRAMS`).
        **kwargs: Forwarded to the program's :meth:`Program.start`.
    """
    self._teardown_current_program()
    events.clear()        # drop stale input events from before the switch
    self.gesture.reset()  # don't let still-held trigger buttons re-fire
    self.program = self.PROGRAMS[name]
    self.program.make_active_program(self.game)
    self.program.start(**kwargs)
    if config.DEBUG:
      print('loaded program:', name)

  def enter_game_select(self):
    """Interrupt whatever is running and return to the GameSelect hub."""
    self.context = None
    self._activate_program('GameSelect')

  def launch_context(self, target):
    """Start a new context from a menu selection.

    Args:
        target: Either a Program class name (wrapped as a one-item
            :class:`SingleEntryComposer`) or a registered Composer class name.

    Raises:
        KeyError: If ``target`` is neither a known program nor composer.
    """
    if target in self.PROGRAMS:
      self.context = SingleEntryComposer(self.game, target)
    elif target in self.COMPOSER_CLASSES:
      self.context = self.COMPOSER_CLASSES[target](self.game)
    else:
      raise KeyError(f'GameSelect: unknown launch target {target!r}')
    self.context.start()
    self.swap_program()

  def launch_single_program(self, program_name: str):
    """Launch a single program directly (used by the ``-p [Program]`` CLI flag)."""
    self.launch_context(program_name)

  def swap_program(self):
    """Advance the current context, or return home if it is exhausted.

    Called by :meth:`Program.quit`. Advances the current context to its next
    program; when the context is exhausted (or absent) it returns to the
    GameSelect hub.
    """
    if self.context is None or not self.context.next_program():
      return self.enter_game_select()
    self._activate_program(self.context.program_name, **self.context.program_kwargs)

  def update(self, dt):
    """Per-frame tick: check the entry gesture, then update the active program.

    Args:
        dt: Milliseconds since the previous frame.
    """
    # global system trigger: jump to GameSelect from any running program
    if not self._in_game_select() and self.input_manager.changed_state:
      if self.gesture.feed(self.input_manager.state):
        self.gesture.reset()
        return self.enter_game_select()
    # update currently running program
    self.program.update(dt)

##-- END STATE MACHINE --##
##-----------------------##

##########################
### PROGRAM base class ###
#                        #

class Composer:
  """A "show-runner": an ordered script of programs to run as one context.

  Subclasses populate ``program_name_sequence`` (and a matching
  ``program_kwargs_sequence``) in :meth:`load_script`. The state machine calls
  :meth:`next_program` to advance through the script; when it runs off the end,
  :meth:`finish` returns ``None`` and the state machine returns to GameSelect.

  Args:
      game: The :class:`~src.game_loop.Game` instance.
  """
  def __init__(self, game):
    self.game = game
    self.program_index = -1
    self.program_name_sequence = None # subclass must populate this in self.load_script
    self.load_script()

  def load_script(self):
    """Populate the program/kwargs sequences. **Override in subclass.**

    Raises:
        NotImplementedError: If not overridden.
    """
    raise NotImplementedError('Subclass this method!')

  def start(self):
    """Hook called once by the state machine when the context begins."""
    print('composer started')

  def finish(self):
    """Called when the script is exhausted; returns a falsey value."""
    print('Composer script is complete.')
    return None

  @property
  def program_name(self):
    """Class name of the program at the current index."""
    return self.program_name_sequence[self.program_index]

  @property
  def program_kwargs(self):
    """Start-kwargs for the program at the current index."""
    return self.program_kwargs_sequence[self.program_index]

  def next_program(self):
    """Advance to the next program.

    Returns:
        True if there is a next program, else the result of :meth:`finish`
        (``None``), signalling the context is complete.
    """
    self.program_index += 1

    if self.program_index == len(self.program_name_sequence):
      return self.finish()

    return True

class SingleEntryComposer(Composer):
  """A one-program context, used when GameSelect launches a single game.

  Args:
      game: The :class:`~src.game_loop.Game` instance.
      program_name: Class name of the single program to run.
  """
  def __init__(self, game, program_name):
    self._program_name = program_name
    super().__init__(game)

  def load_script(self):
    self.program_name_sequence = [self._program_name]
    self.program_kwargs_sequence = [dict()]


@StateMachine.register_composer
class BirthdayComposer(Composer):
  """The original birthday show: a fixed sequence of games with clue audio."""
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
    """Base class for every mini-game.

    Subclass this, put the module in the ``programs`` directory, and instantiate
    it once at the bottom of the module so it registers itself. Override
    :meth:`start` (setup) and :meth:`update` (per-frame logic); call
    ``super().update(dt)`` so cooldown/scheduler bookkeeping runs.

    The state machine sets ``self.game`` and ``self.input_manager`` via
    :meth:`make_active_program` before :meth:`start` is called.

    Class Attributes:
        system_triggers (dict): Reserved for system-wide triggers (TODO).
        triggers (dict): Optional single-state -> action map.
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
        self._tick = 0
        # per-instance scheduler/cooldowns (must NOT be shared across programs)
        self.scheduler = []   # heap of (deadline_ms, schedule_id, fn)
        self.cooldowns = {}   # button_id -> deadline_ms
        self.schedule_id = 0

    @property
    def tick(self):
      """Frame counter for this program. Read-only; increments once per frame.

      A pure frame index for frame-based bookkeeping -- **not** a clock. Anything
      that needs a real duration (timeouts, cooldowns, scheduled callbacks) must
      use :attr:`now_ms`, which is robust to frame-rate variation.
      """
      return self._tick

    @property
    def now_ms(self):
      """Monotonic game-loop time in ms (see :attr:`Game.now_ms`).

      The single timeline for every deadline this program sets or checks. It only
      moves forward and is immune to wall-clock jumps, so durations measured
      against it are always correct.
      """
      return self.game.now_ms

    def update(self, dt):
        """Per-frame update. **Override in subclass** (and call ``super()``).

        The base implementation runs cooldown and scheduler bookkeeping and
        advances the tick counter.

        Args:
            dt: Milliseconds since the previous frame.
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
      """Called when the program becomes active. **Override in subclass.**

      May accept keyword arguments supplied by the context's
      ``program_kwargs``.
      """
      return RuntimeError('override this method in subclass')

    def quit(self, next_program=None):
      """Finish this program and hand control back to the state machine."""
      print('Program base class quit method called.')
      self.game.state_machine.swap_program()

    def teardown(self):
      """Drop this program's pending callbacks and cooldowns.

      Called by the state machine when switching away (which also stops audio,
      kills animations, and clears the lasers). Override to release anything
      unusual you started, but call ``super().teardown()``.
      """
      self.scheduler = []
      self.cooldowns = {}

    def make_active_program(self, game):
        """Bind the game reference and input manager. Called before :meth:`start`."""
        self.game = game
        self.input_manager = self.game.input_manager
#        self.start()
#        if config.DEBUG:
#            print('loaded program: ', self.__class__.__name__)

    def after(self, ms, func, *args, **kwargs):
        """Schedule ``func(*args, **kwargs)`` to run ``ms`` milliseconds from now.

        Callbacks run from :meth:`check_schedule` during :meth:`update`. Pending
        callbacks are dropped on :meth:`teardown`.

        Args:
            ms: Delay in milliseconds.
            func: Callable to invoke.
            *args: Positional args for ``func``.
            **kwargs: Keyword args for ``func``.
        """
        deadline = self.now_ms + ms
        f = lambda: func(*args, **kwargs)
        heappush(self.scheduler, (deadline, self.schedule_id, f))
        self.schedule_id += 1

    def check_schedule(self):
        """Run any scheduled callbacks whose deadline has passed."""
        if self.scheduler:
            now = self.now_ms
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
        """Mark ``button_id`` as on cooldown for ``ms`` milliseconds.

        Use with ``if button_id not in self.cooldowns`` to debounce/rate-limit
        actions on held or bouncing buttons.
        """
        self.cooldowns[button_id] = self.now_ms + ms  # default: quarter-second

    def check_cooldowns(self):
        """Expire any cooldowns whose deadline has passed."""
        to_free = []
        for button_id, deadline_ms in self.cooldowns.items():
            if self.now_ms - deadline_ms > 0:
                to_free.append(button_id)
        for button_id in to_free:
            self.cooldowns.pop(button_id)

    def match_triggers(self, state):
        """Return the action mapped to ``state``, or :meth:`default_action`."""
        # match any single-state trigger
        action = self.triggers.get(state, self.default_action)
        return action

    def match_sequence_triggers(self, maxlen):
        """Return the action for the first matching sequence trigger, or :meth:`no_action`."""
        # match any sequence-of-states trigger
        seq = self.input_manager.get_history_sequence(n=maxlen)
        for trig_seq, action in self.sequence_triggers.items():
            if trig_seq.match(seq):
                return action
        return self.no_action


    def default_action(self, state: 'State'):
        """Fallback trigger action. Override if you use :meth:`match_triggers`."""
        raise RuntimeError('default_action needs to be implemented in Program subclass.')

    def no_action(self, state: 'State'):
        """A trigger action that does nothing."""
        return None
