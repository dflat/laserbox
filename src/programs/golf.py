from .base import *
from ..event_loop import *
import random
import time
import math
import inspect
from math import sin, pi, floor

class Golf(Program):
    def __init__(self):
        super().__init__()
        self.remap = [0,13,1,12,2,11,3,10,4,9,5,8] # ascending laser ports from control room
        #self.remap = dict(zip(range(14),[13,0,12,1,11,2,10,3,9,4,8,5]))
        self.sound_a = 'lasers/00_High.wav'

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

    def start(self):
        print('starting')
        self.game.mixer.load_effect(self.sound_a)
        self.reset()

    def reset(self,goal=13):
        self.swinging = False
        self.rolling = False
        self.max_roll_time = 5
        self.prev_displacement_index = 0
        self.goal = goal
        print("goal:",self.goal)
        self.set_word(0)

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

    def start_rolling(self):
        print(inspect.stack()[0][3])
        self.rolling = True
        self.roll_start = time.time()

    def stop_rolling(self):
        print(inspect.stack()[0][3])
        self.rolling = False

    def set_word(self, word, with_target = True):
        if with_target:
            word |= 2**self.goal
        self.game.lasers.set_word(word)

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
            print(f'****{displacement_index}****')
            self.play_laser_sound()
            self.set_word(1<<displacement_index)
            self.prev_displacement_index = displacement_index

        elif roll_time > self.max_roll_time:
            self.stop_rolling()
            self.grade_roll(displacement_index)

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
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
