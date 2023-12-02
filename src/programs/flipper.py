from .base import *
from ..event_loop import *
from ..animation import random_k_dance
import random
import time


class Flipper(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed

    def create_board(self,n=6):
        board = [0]*n
        return board

    def update_laser(self):
        for i in range(len(self.board)):
            if self.board[i] == 1:
                self.game.lasers.turn_on(i)
            else:
                self.game.lasers.turn_off(i)

    def create_board_pattern(self, diffuclty=0): # diffuclty 0 = easy, 1 = medium, 2 = hard
        for i in range(len(self.board)):
            state = random.randint(0,1)
            self.board[i] = state
        self.update_laser()

    def flip(self,pos):
        self.board[pos]= int(not(self.board[pos]))

    def check_for_win(self):
        return all(self.board)

    def victory_dance(self,t=5,k=3, delay = 0.1):
        self.win_animation.start()
        self.game.mixer.play_effect(self.win_sound)
        self.after(self.win_dur*1000, self.reset_board)

    def reset_board(self):
        self.won = False
        self.board = self.create_board()
        self.game.lasers.set_word(0)

    def start(self):
        self.game.mixer.load_music('Nightcall22050.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1

        self.win_sound = 'congrats_extended.wav'
        self.game.mixer.load_effect(self.win_sound)
        self.win_dur = self.game.mixer.effects[self.win_sound].get_length()
        self.win_animation = random_k_dance(k=3,fps=6 , dur=self.win_dur - 1.2)
        self.board = self.create_board()
        self.create_board_pattern()
        self.won = False

    def button_pressed(self, state: State):
        print('clue finder got:', state, int(state))

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        if self.won:
            self.after(2000, self.victory_dance)
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                #print('button down:', event.key)
                #self.game.mixer.play_by_id(event.key)
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
                self.create_board_pattern()
                won = False


        self.won = self.check_for_win()
 

    def default_action(self, state: 'State'):
        self.button_presssed(state)

Flipper()
