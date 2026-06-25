"""Golf: a timing/power mini-game played across the laser row.

Hold a button to charge power (a sine wave drives a growing bar of lit lasers),
release to "swing". The ball then "rolls" along the lasers with exponential
decay and comes to rest on a port; land on the blinking target hole to score.
A spoken voice gives feedback on how close you were. Score
``config.Golf.GOALS_TO_COMPLETE`` goals to finish.
"""
from .base import *
from ..event_loop import *
from ..config import config
from ..animation import random_k_dance
import random
import os
import math
import inspect
import pygame
from math import sin, pi, floor

class Golf(Program):
    """Charge-and-release golf: stop the rolling ball on the blinking target."""

    def __init__(self):
        super().__init__()
        self.buttons = [0,1,2,3,4,5] # allow any of these to trigger swing
        self.remap = [0,13,1,12,2,11,3,10,4,9,5,8] # ascending laser ports from control room
        self.init_sound_feedback()
        self.init_blink_duty_cycle()

    def init_sound_feedback(self):
        """Set the music, effect, patch, and voice-feedback asset paths."""
        self.music = 'Golf2Slow.wav'
        self.fall_off_sound = 'splash_mono.wav'
        self.advance_port_sound = os.path.join('positive', 'arcade_plus_one.wav')
        self.win_sound = os.path.join('positive', 'hooray.wav')
        self.congrats_sound = os.path.join('positive', 'congrats_extended.wav')
        self.patch = 'kicks_ascending_mono'   # sounds to play as laser "rolls" along increasing "holes"
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
        """Precompute the on/off durations (ms) for blinking the target hole."""
        self.blink_fps = 3                  # frequency of "target hole" laser blinks
        self.blink_duty_cycle = .5         # percent of cycle to keep laser ON
        blink_period_ms = 1000 / self.blink_fps                        # one duty cycle, ms
        blink_on_ms = self.blink_duty_cycle * blink_period_ms          # ON portion, ms
        blink_off_ms = (1 - self.blink_duty_cycle) * blink_period_ms   # OFF portion, ms
        self.blink_ms_to_wait = [blink_off_ms, blink_on_ms]            # indexed by blink_on flag

    def start(self):
        """Load audio/animation assets, init round state, and deal the first goal."""
        print('starting')
        self.program_t = 0
        self.blink_on = True
        self.word = 0
        self.prev_word = None
        self.release_pending = { } # used for anti-jitter protection on physical button release
        self.last_blink_toggle = 0
        self.goals_scored = 0
        self.goals_to_complete = config.Golf.GOALS_TO_COMPLETE #3
        pygame.mixer.music.set_volume(1)
        self.game.mixer.load_music(self.music, fade_ms=2000)
        self.game.mixer.load_effect(self.fall_off_sound, volume=0.5)
        self.game.mixer.load_effect(self.win_sound, volume=0.4)
        self.game.mixer.load_effect(self.advance_port_sound, volume=0.3)
        self.game.mixer.load_effect(self.congrats_sound, volume=config.CONGRATS_VOL)
        for feedback in self.voice_feedback:
            self.game.mixer.load_effect(feedback)
        self.game.mixer.use_patch(self.patch)
        self.congrats_dur = self.game.mixer.effects[self.congrats_sound].get_length()
        self.win_animation = random_k_dance(k=3, fps=8, dur=max(0,self.congrats_dur-1.2))
        self.reset()

    def reset(self, goal=13, tries_left=3):
        """Start a new round/attempt: clear state and set the target ``goal``."""
        self.tries_left = tries_left
        print('tries left:', tries_left)
        self.swinging = False
        self.rolling = False
        self.grading = False
        self.max_roll_time = 5
        self.prev_displacement_index = -1
        self.goal = goal
        self.roll_port_index = 0
        print("new goal is:",self.goal)
        self.set_word(0)

    def update_blink_animation(self):
        """Toggle the blinking target hole at the configured duty cycle."""
        elapsed = self.program_t - self.last_blink_toggle
        if elapsed >= self.blink_ms_to_wait[self.blink_on]:
            self.blink_on = not self.blink_on
            self.last_blink_toggle = self.program_t
            #if not (self.swinging or self.rolling):
            #    self.set_word(0)
            self.refresh_word() # blink even if no one is calling set_word (e.g. in waiting state)
            #self.game.lasers.set_value(self.goal, self.blink_on)

    def get_velocity(self, t, max_v=20, max_pow=12.9):
        """Compute swing power/velocity from the charge time ``t`` (sine curve)."""
        s = 0.5 + 0.5*sin(2*pi*t/2 - pi/2)
        self.power_index = floor(max_pow*s)
        #print(self.power_index)
        self.v = max_v*s

    def get_displacement_index(self, t, c=1):
        """Return the laser index the ball has reached at roll time ``t``.

        Uses exponential decay toward ``v/c``. Returns None if the ball rolls
        off the end (index > 13).
        """
        self.d = -(self.v/c)*(math.e**(-c*t)) + self.v/c
        index = math.floor(self.d)
        if index > 13:
            return None
        return index

    def start_swinging(self):
        """Begin charging the swing (records the start time)."""
        #print(inspect.stack()[0][3])
        self.swinging = True
        self.swing_start = self.now_ms

    def stop_swinging(self):
        """End charging; freeze the final power and the resting displacement."""
        if not self.swinging:
            print('erroneous call to stop_swinging ignored.')
            return
        #print(inspect.stack()[0][3])
        self.swinging = False
        self.set_word(0)
        self.end_displacement_index = self.get_displacement_index(t=self.max_roll_time)

    def start_rolling(self):
        """Begin the rolling phase (records the start time)."""
        if self.rolling:
            print('erroneous call to start_rolling ignored.')
            return
        #print(inspect.stack()[0][3])
        self.rolling = True
        self.roll_start = self.now_ms

    def stop_rolling(self):
        """End the rolling phase."""
        #print(inspect.stack()[0][3])
        self.rolling = False

    def set_word(self, word, with_target = True):
        """Write ``word`` to the lasers, OR-ing in the blinking target hole.

        Args:
            word: The base laser bitmask (cached without the target bit).
            with_target: If True and the blink is on, also light the target.
        """
        self.prev_word = word # cache word without goal bit or'd in
        if with_target and self.blink_on:
            word |= 2**self.goal
        #print('set word:', word)
        self.game.lasers.set_word(word)

    def refresh_word(self):
        """Re-apply the cached word (used to keep the target blinking)."""
        self.set_word(self.prev_word)

    def fall_off(self):
        """Handle the ball rolling off the end: clear lasers, play the splash."""
        print(inspect.stack()[0][3])
        self.set_word(0, with_target = False)
        self.game.mixer.play_effect(self.fall_off_sound)

    def celebrate(self):
        """Score the goal; finish the game or set up the next round."""
        print('you won!')
        self.goals_scored += 1
        self.game.mixer.play_effect(self.win_sound)
        if self.goals_scored >= self.goals_to_complete:
            pygame.mixer.music.fadeout(3000)
            self.after(3000, self.complete)
        # say 'starting new round (TODO)'
        else:
            self.after(3000, self.reset, random.randint(8,13))

    def complete(self):
        """Play the final celebration, then quit after it finishes."""
        self.game.mixer.play_effect(self.congrats_sound)
        self.win_animation.start()
        print('golf game complete...')
        self.after(self.congrats_dur*1000, self.quit)
        #self.advance_program_or_exit() # TODO

    def quit(self):
        """Hand control back to the state machine."""
        # cleanup
        super().quit()

    def play_voice_feedback(self, displacement_index):
        """Play a spoken line describing how close the ball stopped to the goal."""
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
        """Advance the rolling ball one frame: light its port, sound it, or stop."""
        roll_time = (self.now_ms - self.roll_start) / 1000  # seconds
        displacement_index = self.get_displacement_index(roll_time)
        if displacement_index is None:
            # ball has rolled off the edge.
            self.fall_off()
            return self.grade_roll(displacement_index)

        if displacement_index > self.prev_displacement_index:
            # ball has advanced forward one space.
            #print(f'**{displacement_index}**')
            self.game.mixer.play_by_id(displacement_index, duck=False)
            #self.game.mixer.play_effect(self.advance_port_sound)
            self.set_word(1 << displacement_index)
            self.prev_displacement_index = displacement_index

        #elif roll_time > self.max_roll_time:
        if displacement_index == self.end_displacement_index:
            # ball has come to a stop.
            # note: should there be a delay here?
            #print('reached end port (ball stopped) at:', displacement_index)
            self.grade_roll(displacement_index)

    def grade_roll(self, displacement_index):
        """Judge where the ball stopped: win, retry, or start a new round."""
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

    def release_pending_buttons(self):
        """Anti-jitter: after a short delay, treat a button release as a swing.

        Adds a small delay before acting on a physical release so contact
        bounce doesn't trigger a premature swing.
        """
        to_release = []
        for key, deadline in self.release_pending.items():
            if self.now_ms - deadline > 0:
                # deadline has passed, trigger action
                to_release.append(key)
                self.stop_swinging()
                self.start_rolling()
        for key in to_release:
            print('realeasing', key)
            self.release_pending.pop(key)


    def update(self, dt):
        """Per-frame: drive blink/charge/roll, and handle button & toggle events."""
        super().update(dt)
        self.update_blink_animation()
        self.program_t += dt

        if self.swinging:
            self.get_velocity((self.now_ms - self.swing_start) / 1000)  # seconds
            self.set_word(sum(2**i for i in self.remap[:self.power_index]))

        elif self.rolling:
            self.roll()

        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                print('button down fired')
                if self.release_pending.get(event.key):
                    # button re-engaged in release anti-jitter interval; cancel pending swing release
                    print('*cancelled pending swing release*')
                    self.release_pending.pop(event.key)
                if event.key in self.buttons and not (self.swinging or self.rolling or self.grading):
                    self.start_swinging()

            elif event.type == EventType.BUTTON_UP:
                print('button up fired')
                # anti-jitter protection
                if event.key in self.buttons and self.swinging and not (self.rolling or self.grading):
                    # make sure no release is currently pending
                    if self.release_pending:
                        continue
                    else:
                        self.release_pending[event.key] = (
                            self.now_ms + config.ANTI_JITTER_DELAY * 1000)

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.reset(random.randint(8,13))

        # anti-jitter protection
        self.release_pending_buttons()

Golf()
