"""The event system: event types and the global event queue.

Input is turned into :class:`Event` objects by
:class:`~src.io_managers.InputManager` and pushed onto the singleton
:data:`events` queue. The active program drains the queue each frame with
``for event in events.get(): ...``. A bounded history is also kept for
sequence/trigger matching.
"""
from enum import IntEnum
from queue import Queue
from collections import deque

class EventType(IntEnum):
    """Enumeration of event kinds carried by :class:`Event.type`."""
    NONE = 0
    DEFAULT = 1
    SOUND_END = 2
    STATE_CHANGE = 3
    BUTTON_DOWN = 4
    BUTTON_UP = 5
    TOGGLE_ON = 6
    TOGGLE_OFF = 7

class Event:
    """Base event. Arbitrary keyword attributes are attached on construction.

    Input events carry ``key`` (button/toggle id) and ``state`` (the full
    :class:`~src.programs.base.State` at the time of the event).

    Class Attributes:
        type (EventType): The event's kind.
        types (list): Per-family registry of member ``EventType`` values.
    """
    type = EventType.DEFAULT
    types = []
    def __init__(self, **kwargs):
        self.has_callback = False
        for name, attr in kwargs.items():
            setattr(self,name,attr)

    def set_callback(self, fn, *args, **kwargs):
        """Attach a callback (and its args) to be invoked by a consumer."""
        self.has_callback = True
        self.callback = fn
        self.args = args
        self.kwargs = kwargs

### Sound Related Events ###

class SoundEvent(Event):
    """Base class for sound-related events."""
    types = []

class SoundEndEvent(SoundEvent):
    """Emitted when a sound finishes playing."""
    type = EventType.SOUND_END

### END Sound Related Events ###


### Input Related Event Types ###

class InputEvent(Event):
    """Base class for input-related events."""
    types = []

class StateChangeEvent(InputEvent):
    """Emitted when the input word changes (currently unused)."""
    type = EventType.STATE_CHANGE
    InputEvent.types.append(type)

class ButtonEvent(InputEvent):
    """Base class for button events."""
    pass

class ButtonDownEvent(ButtonEvent):
    """A button was just pressed (``key`` = button id 0..13)."""
    type = EventType.BUTTON_DOWN
    InputEvent.types.append(type)

class ButtonUpEvent(ButtonEvent):
    """A button was just released (``key`` = button id 0..13)."""
    type = EventType.BUTTON_UP
    InputEvent.types.append(type)

class ToggleEvent(InputEvent):
    """Base class for toggle events (catch with ``isinstance(e, ToggleEvent)``)."""
    pass

class ToggleOnEvent(ToggleEvent):
    """A toggle was switched on (``key`` = toggle id 0..1)."""
    type = EventType.TOGGLE_ON
    InputEvent.types.append(type)

class ToggleOffEvent(ToggleEvent):
    """A toggle was switched off (``key`` = toggle id 0..1)."""
    type = EventType.TOGGLE_OFF
    InputEvent.types.append(type)

### END Input Related Event Types ###


class EventLoop:
    """The global event queue plus a bounded event history (singleton).

    Class Attributes:
        HISTORY_SIZE (int): Number of recent events retained for matching.
        Q_SIZE (int): ``Queue`` maxsize (0 = unbounded).
    """
    HISTORY_SIZE = 500
    Q_SIZE = 0

    def __init__(self):
        self.q = Queue(maxsize=self.Q_SIZE)
        self.history = deque(maxlen=self.HISTORY_SIZE)

    def put(self, event: Event):
        """Enqueue an event and append it to the history."""
        self.q.put(event)
        self.history.append(event) # todo: maybe at to history after consumed (e.g. in get() method) ?

    def clear(self):
        """Drain any unconsumed events.

        Used on program switches so stale input (e.g. the entry-gesture button
        presses) doesn't bleed into the next program.
        """
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except Exception:
                break

    def get_filtered_history(self, types: 'list(EventType)', n=100):
        """Return up to the last ``n`` history events matching ``types``.

        Args:
            types: An ``EventType`` or list of them.
            n: Maximum number of (most recent) matches to return.
        """
        if isinstance(types, EventType): # allow single type arguments
            types = [types]
        return [e for e in self.history if e.type in types][-n:]

    def get(self):
        """Yield and remove every currently-queued event (a one-shot drain)."""
        for i in range(self.q.qsize()):
            try:
                event = self.q.get_nowait()
            except queue.Empty:
                return StopIteration
            yield event

#: The process-wide singleton :class:`EventLoop`.
events = EventLoop() # singleton
