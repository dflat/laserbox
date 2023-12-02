# animation.py #
import random
import os
from .config import config

class Frame:
  def __init__(self, word=None, sound=None, t=None):
    self.word = word 
    self.sound = sound
    self.t = t

  @classmethod
  def from_list(cls, words=None, sounds=None, times=None):
    frames = []
    for i in range(len(words)):
      frame = Frame(words[i] if words else None,
                    sounds[i] if sounds else None,
                    times[i] if times else None )
      frames.append(frame)
    return frames

class FrameSequence:
  DEFAULT_FRAME_T = 100 # ms per frame

  def __init__(self, frames: 'list(Frame)', timing_track=None, func=None):
    self.frames = frames
    self.timing_track = timing_track or [self.DEFAULT_FRAME_T]*len(frames)
    self.last_frame_index = len(frames) - 1
    self.func = func

  def __getitem__(self, index):
    return self.frames[index]

  @classmethod
  def by_fps(cls, frames, fps):
    frame_t = 1000 / fps
    return cls(frames=frames, timing_track=[frame_t]*len(frames))

  @classmethod
  def by_dur(cls, frames, dur):
    frame_t = dur / len(frames)
    return cls(frames=frames, timing_track=[frame_t]*len(frames))


class DynamicFrameSequence(FrameSequence):
  def __init__(self, n_frames, func=None, timing_track=None):
    self.frames = [Frame()]*n_frames
    self.timing_track = timing_track or [self.DEFAULT_FRAME_T]*n_frames
    self.n_frames = n_frames
    self.func = func or self.random
    self.last_frame_index = n_frames - 1


  def random(self, frame):
    return Frame(word=random.randint(0,2**14-1))

  @classmethod
  def by_fps(cls, func, n_frames, fps):
    frame_t = 1000 / fps
    return cls(func=func, n_frames=n_frames, timing_track=[frame_t]*n_frames)


class Animation:
  """
  This class may be subclassed with methods provided
  for self.set_up, self.check_for_next_frame, and self.play_frame.
  Done callback function may be provided during initialization or
  overridden in subclass.
  """
  currently_running = { }
  finished = { }
  _anim_id = 0
  game = None

  def __init__(self, frames: FrameSequence, loops=0, done_callback=None):
    """
    ::loops:: is the number of loops to play *after* the first loop finishes. If
    """
    self.frames = frames
    self.epsilon = 1000/config.FPS/2 # half the length of an update tick in ms

    self._loops = loops
    self.loops = loops
    self.done = done_callback or self.done

    self.anim_id = self._anim_id
    self.anim_id += 1

  @classmethod
  def update_all(cls, dt):
    for anim_id, animation in cls.currently_running.items():
      animation.update(dt)

    for anim_id in cls.finished:
        cls.currently_running.pop(anim_id)
    cls.finished = { }
    
  def start(self):
    """
    Do not override. Called before ::self.set_up:: on animation start.
    """
    self.t = 0        # elapsed time since animation started
    self.tick_no = 0  # incremented on each game frame
    self.frame_no = 0
    self.time_left_in_frame = self.frames.timing_track[0]
    self.__class__.currently_running[self.anim_id] = self
    self.set_up()

  def advance_frame(self):
    residual = self.time_left_in_frame
    print(f'residual:{residual:.1f}')
    self.frame_no += 1
    if self.frame_no > self.frames.last_frame_index:
      return self.finish()
    self.frame_length = self.frames.timing_track[self.frame_no]
    self.time_left_in_frame = self.frame_length + residual # negative residual will shorten next frame, & vice versa

  def frame_ready(self):
    if self.time_left_in_frame < self.epsilon:
      return True

  def update(self, dt):
    """
    Do not override. Called once per game frame, and drives animation. ::dt:: in ms.
    """
    self.tick_no += 1
    self.t += dt 
    self.time_left_in_frame -= dt

    if self.frame_ready():
      self.play_frame() # game ref not necessary here, it is stuck on the class object instead (TODO)
      self.advance_frame()

  def finish(self):
    """
    Do not override. Called before ::self.done:: on animation end.
    """
    if self.loops > 0:
      self.loops -= 1
      return self.start()
    self.loops = self._loops
    self.done()
    self.finished[self.anim_id] = self


  def set_up(self):
    """
    Should be overridden by user in subclass or as callback on Animation init.
    Included here as a default / example.
    """
    #self.frames = [2**i for i in range(14)] + [2**i for i in reversed(range(13))]
    # files stored in assets/sounds/effects
    #sound_effects = [os.path.join('lasers', i) for i in ('00_High.wav', '01_Mid.wav', '02_Low.wav')]
    #for filename in sound_effects:
        #self.game.mixer.load_effect(filename)
    #    pass
    #self.audio_frames = [random.choice(sound_effects) for _ in range(len(self.frames))]
    #frame_time = .1
    #self.frame_times = [frame_time*i for i in range(len(self.frames))]
    #print('animation set_up finished.')
    pass

  def play_frame(self):
      """
      ::game:: object reference is inserted on the Animation class object by Game.__init__ .
      """
      frame = self.frames[self.frame_no] # uses complete word here, but could instead turn individual lasers on/off
      if self.frames.func:
        frame = self.frames.func(frame) # todo: what arguments if any to provide to func? could it be used to modify current frame before
                # playback?
      if frame.word:
        self.game.lasers.set_word(frame.word)
      if frame.sound:
        self.game.mixer.play_effect(frame.sound)

  def done(self):
    """
    Should be overridden by user in subclass or as callback on Animation init.
    Included here as a default / example.
    """
    self.game.lasers.set_word(0)
    print(f'Animation {self.anim_id} ended.')

  @staticmethod
  def rescale(x, a=0, b=1):
    """
    Linearly interpolate between a and b. Override this function
    for other timing function (e.g. quadratic or sinusoidal).
    """
    return min(b, a + x*(b-a))

class ThreadedAnimation:
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

# example Animation factories
def ping_pong(fps=5, loops=3):
  word_frames =  [2**i for i in range(14)] + [2**i for i in reversed(range(1,13))]
  sound_frames = None #[os.path.join('lasers', '02_Low.wav')]*len(word_frames)
  frames = Frame.from_list(words=word_frames, sounds=sound_frames)
  frame_seq = FrameSequence.by_fps(frames=frames, fps=fps)
  return Animation(frames=frame_seq, loops=loops)

def random_k_dance(k=3, fps=5, dur=10):
  n_frames = int(dur * fps)
  def func(frame):
    return Frame(word=sum(1 << random.randint(0,13) for _ in range(k)))
  frame_seq = DynamicFrameSequence.by_fps(func, n_frames, fps)
  return Animation(frames=frame_seq)

