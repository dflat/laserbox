"""Flipper: a "Lights Out" style puzzle on 6 lasers.

Pressing a button toggles its laser and its immediate neighbours. The round is
won when all six lasers are on. A toggle switch reshuffles the board.
"""
from .base import *
from ..event_loop import *
from ..animation import random_k_dance
from ..config import config
import pygame
import random
import time
import os


class Flipper(Program):
    """Lights-Out puzzle: flip a laser and its neighbours; win when all are on."""

    def __init__(self):
        super().__init__()

    def create_board(self, n=6):
        """Return a fresh all-off board of length ``n``."""
        board = [0]*n
        return board

    def create_board_pattern(self, diffuclty=0, fixed=None):
        """Populate the board (random, or a ``fixed`` pattern) and show it."""
        if fixed:
            # copy, never alias: flip() mutates self.board in place, so binding
            # it directly to a caller-owned list (e.g. config.Flipper.START_BOARD)
            # would corrupt that list across runs and leak state between entries.
            self.board = list(fixed)
            print(fixed)
        else:
            for i in range(len(self.board)):
                state = random.randint(0,1)
                self.board[i] = state
        self.update_laser()

    def update_laser(self):
        """Reflect the current board state onto the lasers."""
        for i in range(len(self.board)):
            self.game.lasers.set_value(i, self.board[i])
#            if self.board[i] == 1:
#                self.game.lasers.turn_on(i)
#            else:
#                self.game.lasers.turn_off(i)

    def flip(self, pos):
        """Toggle the board cell at ``pos``."""
        self.board[pos]= int(not(self.board[pos]))

    def check_for_win(self):
        """True when every board cell is on."""
        return all(self.board)

    def victory_dance(self):
        """Play the win animation + sound, then quit after it finishes."""
        self.win_animation.start()
        self.game.mixer.play_effect(self.congrats_sound)
        self.after(self.win_dur*1000, self.quit)

    def reset_board(self):
        """Clear the board and lasers."""
        self.won = False
        self.board = self.create_board()
        self.game.lasers.set_word(0)

    def quit(self):
        """Reset the board, then hand control back to the state machine."""
        # do any cleanup here
        self.reset_board()
        super().quit()

    def start(self):
        """Load music + win assets and deal the starting board."""
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
        """Apply button flips (cell + neighbours); detect and celebrate a win."""
        super().update(dt)
        if not self.playing:
            return

        if self.won:
            self.playing = False
            pygame.mixer.music.fadeout(2000)
            self.after(1000, self.victory_dance)

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
