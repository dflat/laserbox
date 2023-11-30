from .base import *
from ..event_loop import *
from ..config import config
import random
import time
import math
import inspect
from math import sin, pi, floor

class Golf(Program):
    def __init__(self):
        super().__init__()
        self.remap = [0,13,1,12,2,11,3,10,4,9,5,8] # ascending laser ports from control room
        self.sound_a = 'lasers/00_High.wav'
        self.patch = 'AcousticPlucksHigh'   # sounds to play as laser "rolls" along increasing "holes"
        self.blink_fps = 3                  # frequency of "target hole" laser blinks
        self.blink_duty_cycle = .5          # percent of cycle to keep laser ON
        self.blink_cycle_ticks = config.FPS/self.blink_fps              # ticks in one duty cycle
        blink_on_ticks = int(self.blink_duty_cycle*self.blink_cycle_ticks)   # percent of duty cycle ON
        blink_off_ticks = int((1 - self.blink_duty_cycle)*self.blink_cycle_ticks) # percent of duty OFF
        print('on_ticks, off_ticks:',blink_on_ticks,blink_off_ticks)
        self.ticks_to_wait = [blink_off_ticks, blink_on_ticks]         # indexed by toggle flag

    def start(self):
        print('starting')
        self.ticks = 0
        self.blink_on = True
        self.word = 0
        self.prev_word = None
        self.last_blink_toggle = 0
        self.game.mixer.load_effect(self.sound_a)
        self.game.mixer.use_patch(self.patch)
        self.reset()

    def reset(self,goal=13):
        self.swinging = False
        self.rolling = False
        self.max_roll_time = 5
        self.prev_displacement_index = -1
        self.goal = goal
        self.roll_port_index = 0
        print("goal:",self.goal)
        self.set_word(0)

    def update_blink_animation(self):
        """
        Called every frame to control blinking rate of "target hole"
        """
        elapsed_ticks = self.ticks - self.last_blink_toggle
        if elapsed_ticks >= self.ticks_to_wait[self.blink_on]:
            self.blink_on = not self.blink_on
            self.last_blink_toggle = self.ticks
            #if not (self.swinging or self.rolling):
            #    self.set_word(0)
            self.refresh_word() # blink even if no one is calling set_word (e.g. in waiting state)
            #self.game.lasers.set_value(self.goal, self.blink_on)

    def get_velocity(self,t, max_v=20,max_pow=12.9):
        s = 0.5 + 0.5*sin(2*pi*t/2 - pi/2)
        self.power_index = floor(max_pow*s)
        #print(self.power_index)
        self.v = max_v*s

    def get_displacement_index(self,t,c=1):
        self.d = -(self.v/c)*(math.e**(-c*t)) + self.v/c
        index = math.floor(self.d)
        if index > 13:
            return None
        return index

    def play_laser_sound(self):
        self.game.mixer.play_effect(self.sound_a)

    def start_swinging(self):
        print(inspect.stack()[0][3])
        self.swinging = True
        self.swing_start = time.time()

    def stop_swinging(self):
        print(inspect.stack()[0][3])
        self.swinging = False
        self.set_word(0)

    def fall_off(self):
        print(inspect.stack()[0][3])
        self.set_word(0, with_target = False)
        self.stop_rolling()
        self.play_laser_sound()

    def start_rolling(self):
        print(inspect.stack()[0][3])
        self.rolling = True
        self.roll_start = time.time()

    def stop_rolling(self):
        print(inspect.stack()[0][3])
        self.rolling = False

    def set_word(self, word, with_target = True):
        self.prev_word = word # cache word without goal bit or'd in
        if with_target and self.blink_on:
            word |= 2**self.goal
        #print('set word:', word)
        self.game.lasers.set_word(word)

    def refresh_word(self):
        self.set_word(self.prev_word)

    def grade_roll(self,displacement_index):
        error = abs(self.goal - displacement_index)
        print(f'you scored {error} away from perfect')
        if displacement_index == self.goal:
            self.celebrate()

    def celebrate(self):
        print('you won')

    def roll(self):
        roll_time = time.time() - self.roll_start
        displacement_index = self.get_displacement_index(roll_time)
        if displacement_index is None: #ball has rolled off the edge
            self.fall_off()
        elif displacement_index > self.prev_displacement_index:
            # ball has advanced forward
            print(f'**{displacement_index}**')
            self.game.mixer.play_by_id(displacement_index, duck=False)
            self.set_word(1 << displacement_index)
            self.prev_displacement_index = displacement_index

        elif roll_time > self.max_roll_time:
            self.stop_rolling()
            self.grade_roll(displacement_index)

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        self.update_blink_animation()
        self.ticks += 1
        # check event loop for input changes
        if self.swinging:
            self.get_velocity(time.time() - self.swing_start)
            self.set_word(sum(2**i for i in self.remap[:self.power_index]))
        elif self.rolling:
            self.roll()
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                if event.key == 0 and not (self.swinging or self.rolling):
                    self.start_swinging()
                else:
                    continue
                    
            elif event.type == EventType.BUTTON_UP:
                if event.key == 0 and not self.rolling: 
                    self.stop_swinging()
                    self.start_rolling()

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.reset(random.randint(6,13))

Golf()
