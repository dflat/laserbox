import sys
import time
from collections import deque, namedtuple
import pygame
from .audio_utils import Mixer
from .shift_register import InputShiftRegister, OutputShiftRegister
from .config import config
from .programs import State, StateSequence, StateMachine
from .event_loop import *
if sys.platform == 'linux':
  import RPi.GPIO as GPIO

if '-p' in sys.argv:
    config.START_PROGRAM = sys.argv[2]

class GameClock:
  def __init__(self, FPS):
    self.FPS = FPS
    self.target_dt = 1/FPS
    self.t0 = time.time()
    self.t = self.t0
    self.prev_t = self.t0
    self.frame = 1
    self.target_playhead = 0
    self.actual_playhead = 0
    self.dt_history = deque(maxlen=60*10)
    
  def tick(self, fps):
    self.t = time.time()
    self.target_playhead = self.frame * self.target_dt
    self.actual_playhead = self.t - self.t0
    wait = self.target_playhead - self.actual_playhead
    if wait > 0:
      time.sleep(wait)
    
    dt = self.t - self.prev_t
    self.dt_history.append(dt)
    self.prev_t = self.t
    self.frame += 1
    return dt
  
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

class LaserPort:
  """
  Should only be accessed through LaserBay
  """
  def __init__(self, id):
    self.id = id
    self.on = False
    self.brightness = 1 # not used for now, but possibly implement PWM brightness

  def _turn_on(self):
    self.on = True

  def _turn_off(self):
    self.on = False  

class LaserBay:
  """
  User interacts with this object, which in turn controls
  the state of an array of LaserPort objects.

  Keeps a cache of last state via a 'self.clean' flag.
  """
  def __init__(self, n=14):
    self.n = n
    self.lasers = [LaserPort(i) for i in range(self.n)]
    self.word = 0
    self.clean = True

  def turn_on(self, laser_id):
    """ conveinence method """
    self.set_value(laser_id, 1)

  def turn_off(self, laser_id):
    """ conveinence method """
    self.set_value(laser_id, 0)

  def set_value(self, laser_id, value):
    """
    Set a given laser on or off by it's id.
    """
    self.clean = False
    if value == 1:
      self.lasers[laser_id]._turn_on()
    elif value == 0:
      self.lasers[laser_id]._turn_off()

  def set_word(self, word):
    """
    Set entire word directly, rather than through individual
    laser manipulation.
    """
    self.word = word
    self.clean = True

  def to_word(self):
    """
    If state hasn't changed since to_word was last called
    (as indicated by self.clean) returns the cached word.
    """
    if self.clean:
      return self.word
    self.word = sum(self.lasers[i].on << i for i in range(self.n))
    self.clean = True
    return self.word

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
  

class Animation:
  """
  This class may be subclassed with methods provided
  for self.set_up, self.check_for_next_frame, and self.play_frame.
  Done callback function may be provided during initialization or
  overridden in subclass.
  """
  currently_running = { }
  _anim_id = 0

  def __init__(self, dur, loops=0, done_callback=None):
    self.dur = dur
    self.loops = loops
    self.done = done_callback or self.done

    self.anim_id = self._anim_id
    self.anim_id += 1

  @classmethod
  def update_all(cls, game, dt):
    for anim_id, animation in cls.currently_running.items():
      animation.update(game, dt)

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
      self.start()
    self.done()
    self.currently_running.pop(self.anim_id)


  def set_up(self):
    """
    Should be overridden by user in subclass or as callback on Animation init.
    Included here as a default / example.
    """
    self.frames = [2**i for i in range(13)] + [2**i for i in range(13, 1, -1)]
    # files stored in assets/sounds/effects
    sound_effects = [os.path.join('lasers', i) for i in ('00_High.wav', '01_Mid.wav', '02_Low.wav')]
    for filename in sound_effects:
        self.game.mixer.load_effect(filename)
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

      if audio_frames:
        sound = audio_frames[self.frame_no]
        game.mixer.play_effect(sound)


  def done(self):
    """
    Should be overridden by user in subclass or as callback on Animation init.
    Included here as a default / example.
    """
    print(f'Animation {self.anim_id} ended.')

  @staticmethod
  def rescale(x, a=0, b=1):
    """
    Linearly interpolate between a and b. Override this function
    for other timing function (e.g. quadratic or sinusoidal).
    """
    return min(b, a + x*(b-a))




class Game:
  def __init__(self, PISOreg, SIPOreg, mixer, events):
    self.FPS = config.FPS
    self.input_manager = InputManager(register=PISOreg)
    self.outputs = OutputManager(register=SIPOreg)
    self.lasers = LaserBay(14) # users interact with this to drive laser output
    self.mixer = mixer
    self.events = events # event loop reference (redundant as it is global singleton imported in this module)
    self.state_machine = StateMachine(self)
    self.state_machine.swap_program(config.START_PROGRAM)
    
  def update(self, dt):
    # read input
    self.input_manager.poll()
    changed_state = self.input_manager.changed_state

    # play any ongoing animations
    Animation.update_all(self, dt)

    # update currently running program
    self.state_machine.update(dt)

  def render(self):
    # push output
    laser_state_word = self.lasers.to_word()
    self.outputs.push_word(laser_state_word)

  def run(self):
    self._running = True
    self.t_game_start = time.time()
    self.clock = GameClock(self.FPS)
    dt = 1/self.FPS
    try:
        while True:
          self.update(dt) 
          self.render()
          dt = self.clock.tick(self.FPS)
    except KeyboardInterrupt:
        print('goodbye.')
    except Exception as e:
        print(e)
    finally:
        self.quit()
    
  def quit(self):
    self._running = False
    pygame.quit()
    GPIO.cleanup()
    sys.exit()

if __name__ == "__main__":
    g = Game()
    g.run()
