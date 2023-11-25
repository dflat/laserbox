from .base import *
from ..event_loop import *

class ClueFinder(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }

    def button_pressed(self, state: State):
        print('clue finder got:', state, int(state))

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        # check event loop for input changes
        for event in self.game.events.get():
            if event.type == EventType.BUTTON_DOWN:
                print('button down:', event.key)
                self.game.mixer.play_by_id(event.key)
            elif event.type == EventType.BUTTON_UP:
                print('button up:', event.key)
            elif event.type == EventType.TOGGLE_ON:
                print('toggle_on:', event.key)
            elif event.type == EventType.TOGGLE_OFF:
                print('toggle_off:', event.key)

        # this section/ style of trigger may be defunt (TODO)
        #if self.input_manager.changed_state:
        #    state = State(self.input_manager.state)
        #    action = self.match_triggers(state)
        #    action(state)
        
        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

    def default_action(self, state: 'State'):
        self.button_presssed(state)

ClueFinder()
