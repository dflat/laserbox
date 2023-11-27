# animation.py #
import random
import os

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

  def __init__(self, dur, loops=0, done_callback=None):
    self.dur = dur
    self._loops = loops
    self.loops = loops
    self.done = done_callback or self.done

    self.anim_id = self._anim_id
    self.anim_id += 1

  @classmethod
  def update_all(cls, game, dt):
    for anim_id, animation in cls.currently_running.items():
      animation.update(game, dt)

    for anim_id in cls.finished:
        cls.currently_running.pop(anim_id)
    cls.finished = { }
    
  def start(self):
    """
    Do not override. Called before ::self.set_up:: on animation start.
    """
    self.frames = []  # should be overwritten in self.set_up
    self.audio_frames = [] # should be overwritted in self.set_up if audio is used
    self.frame_no = 0 # incremented by self.next_frame when desired
    self.tick_no = 0  # incremented on each game frame
    self.word = None     # what will be displayed on each frame advance
    self.sound = None
    self.t = 0        # elapsed time since animation started
    self.frame_ready = False
    self.currently_running[self.anim_id] = self
    self.set_up()

  def update(self, game, dt):
    """
    Do not override. Called once per game frame, and drives animation.
    """
    self.t += dt

    frame_ready = self.check_for_next_frame() # checks if ready for next frame
    if frame_ready:
      self.play_frame(game)

    self.tick_no += 1
    #if self.t >= self.dur or self.frame_no >= len(self.frames) - 1:
    if self.frame_no >= len(self.frames) - 1:
      self.finish()

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
    #self.currently_running.pop(self.anim_id)


  def set_up(self):
    """
    Should be overridden by user in subclass or as callback on Animation init.
    Included here as a default / example.
    """
    self.frames = [2**i for i in range(14)] + [2**i for i in reversed(range(13))]
    # files stored in assets/sounds/effects
    sound_effects = [os.path.join('lasers', i) for i in ('00_High.wav', '01_Mid.wav', '02_Low.wav')]
    for filename in sound_effects:
        #self.game.mixer.load_effect(filename)
        pass
    self.audio_frames = [random.choice(sound_effects) for _ in range(len(self.frames))]
    frame_time = .1
    self.frame_times = [frame_time*i for i in range(len(self.frames))]
    print('animation set_up finished.')


  def check_for_next_frame(self):
    """
    Should be overridden by user on Animation init.
    Included here as a default / example.
    """
    # evenly spaced frame playback
    prev_frame_no = self.frame_no
    n = len(self.frames) - 1
    self.frame_no = int(n*self.rescale(self.t / self.dur))

    if self.frame_no > prev_frame_no:
      return True

  def play_frame(self, game):
      """
      Will be called in game loop during main update phase.
      """
      word = self.frames[self.frame_no] # uses complete word here, but could instead turn individual lasers on/off
      game.lasers.set_word(word)

      if self.audio_frames:
        sound = self.audio_frames[self.frame_no]
        game.mixer.play_effect(sound)


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


