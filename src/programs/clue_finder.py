from .base import *

class ClueFinder(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }

    def button_pressed(self, word):
        print('clue finder got:', word, int(word))

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        if self.input_manager.changed_state:
            state = State(self.input_manager.state)
            action = self.match_triggers(state)
            action(state)
        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

    def default_action(self, state: 'State'):
        self.button_presssed(state)

ClueFinder()
