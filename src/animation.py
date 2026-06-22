"""Laser animations: frames, frame sequences, and the animation runner.

A :class:`Frame` is one laser word (+ optional sound). A :class:`FrameSequence`
is an ordered list of frames with per-frame timings; :class:`DynamicFrameSequence`
generates frames on the fly via a function. An :class:`Animation` plays a
sequence over time, driven once per game frame by :meth:`Animation.update_all`.

Animations run globally: the class tracks all running animations and they write
directly to the shared :class:`~src.game_loop.LaserBay` via the ``Animation.game``
reference set by :class:`~src.game_loop.Game`. The factory helpers at the bottom
(:func:`hold_pattern`, :func:`ping_pong`, :func:`random_k_dance`) build ready-to-
start animations.
"""
# animation.py #
import random
import os
from .config import config

class Frame:
  """A single animation frame: a laser ``word`` and/or a ``sound`` to play.

  Args:
      word: 14-bit laser bitmask for this frame (or None to leave lasers as-is).
      sound: Effect filename to play on this frame (or None).
      t: Optional per-frame time (unused by the default timing track).
  """
  def __init__(self, word=None, sound=None, t=None):
    self.word = word
    self.sound = sound
    self.t = t

  @classmethod
  def from_list(cls, words=None, sounds=None, times=None):
    """Build a list of Frames from parallel ``words``/``sounds``/``times`` lists."""
    frames = []
    for i in range(len(words)):
      frame = Frame(words[i] if words else None,
                    sounds[i] if sounds else None,
                    times[i] if times else None )
      frames.append(frame)
    return frames

class FrameSequence:
  """An ordered list of frames plus a per-frame timing track (ms).

  Args:
      frames: List of :class:`Frame`.
      timing_track: Per-frame durations in ms; defaults to ``DEFAULT_FRAME_T``
          for each frame.
      func: Optional per-frame transform applied at playback (see
          :meth:`Animation.play_frame`).
  """
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
    """Construct with a uniform timing track derived from ``fps``."""
    frame_t = 1000 / fps
    return cls(frames=frames, timing_track=[frame_t]*len(frames))

  @classmethod
  def by_dur(cls, frames, dur):
    """Construct so the whole sequence lasts ``dur`` ms."""
    frame_t = dur / len(frames)
    return cls(frames=frames, timing_track=[frame_t]*len(frames))


class DynamicFrameSequence(FrameSequence):
  """A frame sequence whose frames are generated on the fly by ``func``.

  Args:
      n_frames: Number of frames to generate.
      func: ``frame -> Frame`` callable producing each frame at playback time;
          defaults to :meth:`random`.
      timing_track: Per-frame durations in ms.
  """
  def __init__(self, n_frames, func=None, timing_track=None):
    self.frames = [Frame()]*n_frames
    self.timing_track = timing_track or [self.DEFAULT_FRAME_T]*n_frames
    self.n_frames = n_frames
    self.func = func or self.random
    self.last_frame_index = n_frames - 1


  def random(self, frame):
    """Default generator: a fully random 14-bit laser word."""
    return Frame(word=random.randint(0,2**14-1))

  @classmethod
  def by_fps(cls, func, n_frames, fps):
    """Construct with a uniform timing track derived from ``fps``."""
    frame_t = 1000 / fps
    return cls(func=func, n_frames=n_frames, timing_track=[frame_t]*n_frames)


class Animation:
  """Plays a :class:`FrameSequence` over time, writing to the lasers.

  Subclass and override :meth:`set_up`, :meth:`play_frame`, and/or :meth:`done`,
  or pass a ``done_callback``. Build one and call :meth:`start`; the global
  :meth:`update_all` advances it each frame until it finishes.

  Args:
      frames: The :class:`FrameSequence` to play.
      loops: Extra loops after the first pass. ``-1`` loops forever.
      done_callback: Optional callable invoked when the animation ends.

  Class Attributes:
      currently_running (dict): anim_id -> running animation.
      finished (dict): anim_ids that finished this frame (reaped by update_all).
      game: The :class:`~src.game_loop.Game`, injected so frames can drive output.
  """
  currently_running = { }
  finished = { }
  _anim_id = 0
  game = None

  def __init__(self, frames: FrameSequence, loops=0, done_callback=None):
    """See class docstring. ``loops`` is the number of loops *after* the first."""
    self.frames = frames
    self.epsilon = 1000/config.FPS/2 # half the length of an update tick in ms

    self._loops = loops
    self.loops = loops
    self.done = done_callback or self.done

    self.anim_id = self._anim_id
    self._anim_id += 1

  @classmethod
  def update_all(cls, dt):
    """Advance every running animation by ``dt`` ms and reap finished ones."""
    for anim_id, animation in cls.currently_running.items():
      animation.update(dt)

    for anim_id in set(cls.finished):
        cls.currently_running.pop(anim_id)
    cls.finished = { }

  def start(self):
    """Begin playback. Do not override (override :meth:`set_up` instead)."""
    print('animation started with id:', self.anim_id)
    self.t = 0        # elapsed time since animation started
    self.tick_no = 0  # incremented on each game frame
    self.frame_no = 0
    self.time_left_in_frame = self.frames.timing_track[0]
    self.__class__.currently_running[self.anim_id] = self
    self.set_up()

  def advance_frame(self):
    """Move to the next frame, carrying timing residual; finish at the end."""
    residual = self.time_left_in_frame
    print(f'residual:{residual:.1f}')
    self.frame_no += 1
    if self.frame_no > self.frames.last_frame_index:
      return self.finish()
    self.frame_length = self.frames.timing_track[self.frame_no]
    self.time_left_in_frame = self.frame_length + residual # negative residual will shorten next frame, & vice versa

  def frame_ready(self):
    """True when the current frame's time has (nearly) elapsed."""
    if self.time_left_in_frame < self.epsilon:
      return True

  def update(self, dt):
    """Advance the animation by ``dt`` ms. Do not override."""
    self.tick_no += 1
    self.t += dt
    self.time_left_in_frame -= dt

    if self.frame_ready():
      self.play_frame() # game ref not necessary here, it is stuck on the class object instead (TODO)
      self.advance_frame()

  def finish(self):
    """Loop or end the animation. Do not override (override :meth:`done`)."""
    if self.loops == -1:
      return self.start()

    elif self.loops > 0:
      self.loops -= 1
      return self.start()

    self.loops = self._loops
    self.done()
    self.__class__.finished[self.anim_id] = self

  @classmethod
  def kill_by_id(cls, anim_id):
    """Mark a single running animation (by id) to be reaped."""
    anim = cls.currently_running.get(anim_id)
    if anim is not None:
      cls.finished[anim_id] = anim

  @classmethod
  def kill_all(cls):
    """Immediately stop every running animation.

    Used by the StateMachine when tearing down a program so animations don't
    keep driving the lasers into the next program. Does not invoke ``done``
    callbacks.
    """
    cls.currently_running = { }
    cls.finished = { }

  def kill(self):
    """Mark this animation to be reaped on the next :meth:`update_all`."""
    self.__class__.finished[self.anim_id] = self
    print('animation killed with id:', self.anim_id)

  def set_up(self):
    """Run-once setup hook. Override in a subclass or via init; default no-op."""
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
      """Render the current frame: set the laser word and play its sound.

      The ``game`` reference is injected on the class by
      :meth:`Game.__init__ <src.game_loop.Game.__init__>`.
      """
      frame = self.frames[self.frame_no] # uses complete word here, but could instead turn individual lasers on/off
      if self.frames.func:
        frame = self.frames.func(frame) # todo: what arguments if any to provide to func? could it be used to modify current frame before
                # playback?
      if frame.word is not None:
        self.game.lasers.set_word(frame.word)
      if frame.sound:
        self.game.mixer.play_effect(frame.sound)

  def done(self):
    """End hook: clears the lasers. Override in a subclass or via init."""
    self.game.lasers.set_word(0)
    print(f'Animation {self.anim_id} ended.')

  @staticmethod
  def rescale(x, a=0, b=1):
    """Clamp-and-interpolate ``x`` into ``[a, b]`` (override for easing)."""
    return min(b, a + x*(b-a))

class ThreadedAnimation:
  """Placeholder for a future threaded animation variant."""
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

# example Animation factories
def hold_pattern(fps=1, loops=-1, pattern=[1,0,7,0,3,0,0,0]):
  """Build a slow looping animation that cycles through ``pattern`` words."""
  word_frames = pattern # todo: put this in config object
  sound_frames = None
  frames = Frame.from_list(words=word_frames, sounds=sound_frames)
  frame_seq = FrameSequence.by_fps(frames=frames, fps=fps)
  return Animation(frames=frame_seq, loops=loops)

def ping_pong(fps=5, loops=3):
  """Build a single-laser sweep that bounces up and back across the ports."""
  word_frames =  [2**i for i in range(14)] + [2**i for i in reversed(range(1,13))]
  sound_frames = None #[os.path.join('lasers', '02_Low.wav')]*len(word_frames)
  frames = Frame.from_list(words=word_frames, sounds=sound_frames)
  frame_seq = FrameSequence.by_fps(frames=frames, fps=fps)
  return Animation(frames=frame_seq, loops=loops)

def random_k_dance(k=3, fps=5, dur=10):
  """Build a celebratory animation flashing ``k`` random lasers per frame.

  Args:
      k: Number of lasers lit each frame.
      fps: Frames per second.
      dur: Total duration in seconds.
  """
  n_frames = int(dur * fps)
  def func(frame):
    return Frame(word=sum(1 << random.randint(0,13) for _ in range(k)))
  frame_seq = DynamicFrameSequence.by_fps(func, n_frames, fps)
  return Animation(frames=frame_seq)
