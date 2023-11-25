from .base import *
from ..event_loop import *

class ClueFinder(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }
        self.patch_map = {  0: 'nouns',
                            1: 'verbs',
                            2: 'adverbs',
                            3: 'articles_and_preps'}

    def start(self):
        self.game.mixer.use_patch(self.patch_map[0])
        #self.game.mixer.load_music('Nightcall.wav')
        #self.game.mixer.set_music_volume(.1)
        #self.game.mixer.VOL_HIGH = 0.3
        
    def button_pressed(self, state: State):
        print('clue finder got:', state, int(state))

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                #print('button down:', event.key)
                self.game.mixer.play_by_id(event.key)
                #self.game.lasers[event.key].turn_on()
            elif event.type == EventType.BUTTON_UP:
                pass
                #print('button up:', event.key)
                #self.game.lasers[event.key].turn_off()

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.game.mixer.use_patch(self.patch_map[toggle_state])

        # this section/ style of trigger may be defunt (TODO)
        #if self.input_manager.changed_state:
        #    state = State(self.input_manager.state)
        #    action = self.match_triggers(state)
        #    action(state)

        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

    def default_action(self, state: 'State'):
        self.button_presssed(state)

ClueFinder()
