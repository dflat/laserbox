from enum import IntEnum
from queue import Queue
from collections import deque

class EventType(IntEnum):
    NONE = 0
    DEFAULT = 1
    SOUND_END = 2
    STATE_CHANGE = 3
    BUTTON_DOWN = 4
    BUTTON_UP = 5
    TOGGLE_ON = 6
    TOGGLE_OFF = 7
    
class Event:
    type = EventType.DEFAULT
    types = []
    def __init__(self, **kwargs):
        self.has_callback = False
        for name, attr in kwargs.items():
            setattr(self,name,attr) 

    def set_callback(self, fn, *args, **kwargs):
        self.has_callback = True
        self.callback = fn
        self.args = args
        self.kwargs = kwargs

### Sound Related Events ###

class SoundEvent(Event):
    types = []
    
class SoundEndEvent(SoundEvent):
    type = EventType.SOUND_END

### END Sound Related Events ###


### Input Related Event Types ###

class InputEvent(Event):
    types = []

class StateChangeEvent(InputEvent):
    type = EventType.STATE_CHANGE
    InputEvent.types.append(type)

class ButtonEvent(InputEvent):
    pass

class ButtonDownEvent(ButtonEvent):
    type = EventType.BUTTON_DOWN 
    InputEvent.types.append(type)

class ButtonUpEvent(ButtonEvent):
    type = EventType.BUTTON_UP
    InputEvent.types.append(type)

class ToggleEvent(InputEvent):
    pass

class ToggleOnEvent(ToggleEvent):
    type = EventType.TOGGLE_ON
    InputEvent.types.append(type)

class ToggleOffEvent(ToggleEvent):
    type = EventType.TOGGLE_OFF
    InputEvent.types.append(type)

### END Input Related Event Types ###


class EventLoop:
    """singlton"""
    HISTORY_SIZE = 500
    Q_SIZE = 0

    def __init__(self):
        self.q = Queue(maxsize=self.Q_SIZE)
        self.history = deque(maxlen=self.HISTORY_SIZE)

    def put(self, event: Event):
        self.q.put(event)
        self.history.append(event) # todo: maybe at to history after consumed (e.g. in get() method) ?

    def get_filtered_history(self, types: 'list(EventType)', n=100):
        if isinstance(types, EventType): # allow single type arguments
            types = [types]
        return [e for e in self.history if e.type in types][-n:]

    def get(self):
        for i in range(self.q.qsize()):
            try:
                event = self.q.get_nowait()
            except queue.Empty:
                return StopIteration
            yield event

events = EventLoop() # singleton
