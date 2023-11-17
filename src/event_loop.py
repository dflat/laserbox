from enum import IntEnum
from queue import Queue

class EventType(IntEnum):
    NONE = 0
    DEFAULT = 1
    SOUND_END = 2
    
class Event:
    type = EventType.DEFAULT
    def __init__(self,**kwargs):
        self.has_callback = False
        for name, attr in kwargs.items():
            setattr(self,name,attr) 

    def set_callback(self, fn, *args, **kwargs):
        self.has_callback = True
        self.callback = fn
        self.args = args
        self.kwargs = kwargs

class SoundEndEvent(Event):
    type = EventType.SOUND_END

class EventLoop:
    """singlton"""
    def __init__(self):
        self.q = Queue()
    def put(self, event: Event):
        self.q.put(event)
    def get(self):
        for i in range(self.q.qsize()):
            try:
                event = self.q.get_nowait()
            except queue.Empty:
                return StopIteration
            yield event
