from .base import *
from ..event_loop import *
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
        time.sleep(.5)
        t0 = time.time()
        t_now = 0
        while t_now < t:
            word = sum(2**random.randint(0,13) for _ in range(k))
            self.game.outputs.push_word(word)
            t_now = time.time() - t0
            time.sleep(delay)

    def reset_board(self):
        self.won = False
        self.board = self.create_board()
        self.game.lasers.set_word(0)

    def start(self):
        self.game.mixer.load_music('Nightcall22050.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1

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
            self.victory_dance()
            self.reset_board()
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
