from .base import *
from ..event_loop import *
from ..config import config
import random
import os
import time
import math
import inspect
import pygame
from math import sin, pi, floor
from heapq import heappush, heappop

class Golf(Program):
    def __init__(self):
        super().__init__()
        self.remap = [0,13,1,12,2,11,3,10,4,9,5,8] # ascending laser ports from control room
        self.init_sound_feedback()
        self.init_blink_duty_cycle()
        self.init_scheduler()

    def init_sound_feedback(self):
        self.music = 'Golf2Slow.wav'
        self.sound_a = 'splash.wav'
        self.patch = 'kicks_ascending'   # sounds to play as laser "rolls" along increasing "holes"
        self.voice_feedback = [os.path.join('golf_feedback', name) for name in (
            'trin_perfect.wav',
            'trin_one_away.wav',
            'trin_two_away.wav',
            'trin_undershot_1.wav',
            'trin_overshot_1.wav',
            'trin_overshot_2.wav',
            'trin_overshot_3.wav',
            )]

    def init_blink_duty_cycle(self):
        self.blink_fps = 3                  # frequency of "target hole" laser blinks
        self.blink_duty_cycle = .5         # percent of cycle to keep laser ON
        self.blink_cycle_ticks = config.FPS/self.blink_fps              # ticks in one duty cycle
        blink_on_ticks = int(self.blink_duty_cycle*self.blink_cycle_ticks)   # percent of duty cycle ON
        blink_off_ticks = int((1 - self.blink_duty_cycle)*self.blink_cycle_ticks) # percent of duty OFF
        self.ticks_to_wait = [blink_off_ticks, blink_on_ticks]         # indexed by toggle flag

    def start(self):
        print('starting')
        self.ticks = 0
        self.program_t = 0
        self.blink_on = True
        self.word = 0
        self.prev_word = None
        self.last_blink_toggle = 0
        pygame.mixer.music.set_volume(1)
        self.game.mixer.load_music(self.music, fade_ms=1000)
        self.game.mixer.load_effect(self.sound_a)
        for feedback in self.voice_feedback:
            self.game.mixer.load_effect(feedback)
        self.game.mixer.use_patch(self.patch)
        self.reset()

    def reset(self, goal=13, tries_left=3):
        self.tries_left = tries_left
        print('tries left:', tries_left)
        self.swinging = False
        self.rolling = False
        self.grading = False
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

    def start_swinging(self):
        print(inspect.stack()[0][3])
        self.swinging = True
        self.swing_start = time.time()

    def stop_swinging(self):
        print(inspect.stack()[0][3])
        self.swinging = False
        self.set_word(0)
        self.end_displacement_index = self.get_displacement_index(t=self.max_roll_time)

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

    def fall_off(self):
        print(inspect.stack()[0][3])
        self.set_word(0, with_target = False)
        self.game.mixer.play_effect(self.sound_a)

    def init_scheduler(self):
        self.schedule_id = 0
        self.scheduler = [] # heap

    def after(self, ms, func, *args, **kwargs):
        deadline = time.time() + ms/1000
        f = lambda: func(*args, **kwargs)
        heappush(self.scheduler, (deadline, self.schedule_id, f))
        self.schedule_id += 1

    def check_schedule(self):
        if self.scheduler:
            now = time.time()
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

    def celebrate(self):
        print('you won!')
        # say 'starting new round (TODO)'
        self.after(1000, self.reset, random.randint(8,13))

    def play_voice_feedback(self, displacement_index):
        if displacement_index is None:
            # fell off the edge
            feedback = self.voice_feedback[-1]
        else:
            signed_error = self.goal - displacement_index
            error = abs(signed_error)
            print(f'you scored {error} away from perfect')
            if error < 3:
                # close or perfect
                feedback = self.voice_feedback[error]
            elif signed_error > 0:
                # undershot
                feedback = self.voice_feedback[3]
            else:
                # overshot but didn't fall off
                feedback = random.choice(self.voice_feedback[-3:-1])

        self.game.mixer.play_effect(feedback)

    def roll(self):
        roll_time = time.time() - self.roll_start
        displacement_index = self.get_displacement_index(roll_time)
        if displacement_index is None:
            # ball has rolled off the edge.
            self.fall_off()
            return self.grade_roll(displacement_index)

        if displacement_index > self.prev_displacement_index:
            # ball has advanced forward one space.
            print(f'**{displacement_index}**')
            self.game.mixer.play_by_id(displacement_index, duck=False)
            self.set_word(1 << displacement_index)
            self.prev_displacement_index = displacement_index

        #elif roll_time > self.max_roll_time:
        if displacement_index == self.end_displacement_index:
            # ball has come to a stop.
            # note: should there be a delay here?
            print('reached end port (ball stopped) at:', displacement_index)
            self.grade_roll(displacement_index)

    def grade_roll(self,displacement_index):
        self.stop_rolling()
        self.grading = True
        self.play_voice_feedback(displacement_index)
        if displacement_index == self.goal:
            self.celebrate()
        elif self.tries_left > 1:
            # go on to next try for this round
            self.after(1000, self.reset, self.goal, self.tries_left-1)
        else:
            # missed all tries, round over
            print('You lost this round. Starting new round.')
            self.after(1000, self.reset, random.randint(8,13))




    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        self.update_blink_animation()
        self.check_schedule()
        self.ticks += 1
        self.program_t += dt
        # check event loop for input changes
        if self.swinging:
            self.get_velocity(time.time() - self.swing_start)
            self.set_word(sum(2**i for i in self.remap[:self.power_index]))
        elif self.rolling:
            self.roll()
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                print('button down fired')
                # todo: have a cooldown here
                if event.key == 0 and not (self.swinging or self.rolling or self.grading):
                    self.start_swinging()
                else:
                    continue
                    
            elif event.type == EventType.BUTTON_UP:
                # todo: maybe a cancel timeout here to stop up-jitter
                if event.key == 0 and self.swinging and not (self.rolling or self.grading): 
                    self.stop_swinging()
                    self.start_rolling()

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.reset(random.randint(8,13))

Golf()
