from .base import *
from ..event_loop import *
from ..animation import random_k_dance
from ..config import config
import pygame
import random
import time
import os


class Flipper(Program):
    def __init__(self):
        super().__init__()

    def create_board(self,n=6):
        board = [0]*n
        return board

    def create_board_pattern(self, diffuclty=0, fixed=None): 
        if fixed:
            self.board = fixed
            print(fixed)
        else:
            for i in range(len(self.board)):
                state = random.randint(0,1)
                self.board[i] = state
        self.update_laser()

    def update_laser(self):
        for i in range(len(self.board)):
            self.game.lasers.set_value(i, self.board[i])
#            if self.board[i] == 1:
#                self.game.lasers.turn_on(i)
#            else:
#                self.game.lasers.turn_off(i)

    def flip(self,pos):
        self.board[pos]= int(not(self.board[pos]))

    def check_for_win(self):
        return all(self.board)

    def victory_dance(self):
        self.win_animation.start()
        self.game.mixer.play_effect(self.congrats_sound)
        self.after(self.win_dur*1000, self.reset_board)

    def reset_board(self):
        self.won = False
        self.board = self.create_board()
        self.game.lasers.set_word(0)

    def quit(self, next_program=None):
        # do any cleanup here...
        self.playing = False
        super().quit(next_program)

    def start(self):
        self.game.mixer.load_music('FlipperTutorialTrinity.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1

        self.congrats_sound = os.path.join('positive', 'congrats_extended.wav')
        self.game.mixer.load_effect(self.congrats_sound, volume=config.CONGRATS_VOL)
        self.win_dur = self.game.mixer.effects[self.congrats_sound].get_length()
        self.win_animation = random_k_dance(k=3, fps=6, dur=self.win_dur - 1.2)
        self.board = self.create_board()
        self.create_board_pattern(fixed=config.Flipper.START_BOARD)
        self.won = False
        self.playing = True

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        if not self.playing:
            return

        if self.won:
            pygame.mixer.music.fadeout(2000)
            self.after(1000, self.victory_dance)
            self.quit()

        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                if event.key < len(self.board):
                    pos = event.key
                    left_pos = pos - 1
                    right_pos = pos + 1
                    self.flip(pos)
                    if left_pos >= 0:
                        self.flip(left_pos)
                    if right_pos < len(self.board):
                        self.flip(right_pos)
                    self.update_laser()
            elif event.type == EventType.BUTTON_UP:
                pass

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.create_board_pattern(fixed=False)
                self.won = False

        self.won = self.check_for_win()
 
Flipper()
