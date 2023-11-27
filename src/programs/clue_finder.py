from .base import *
from ..event_loop import *

class ClueFinder(Program):
    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }
        self.patch_map = {  0: 'numbers',
                            1: 'verbs',
                            2: 'adverbs',
                            3: 'articles_and_preps'}

        self.clues = [((0,0),(1,1),(2,0)),
                      ((2,3),(2,2),(2,1))] # (patch_id, button_id)
        self.clue_idx = 0

    def clue_success(self):
        # todo : self.game.lasers.dance()
        self.clue_idx += 1
        if self.clue_idx >= len(self.clues):
            print(f'you found Clue Phrase # {self.clue_idx}!')
            # todo: revert control of game back to state machine, or something
        
    def check_for_clue_success(self, clue_phrase_length=3):
        current_clue = self.clues[self.clue_idx]
        phrase_word_index = 0
        for e in events.get_filtered_history(EventType.BUTTON_DOWN, n=clue_phrase_length):
            candidate_phrase_word = (e.key, e.state.toggles)
            target_phrase_word = current_clue[phrase_word_index]
            if candidate_phrase_word == target_phrase_word:
                phrase_word_index += 1
            if phrase_word_index == clue_phrase_length:
                self.clue_success()



    def start(self):
        self.game.mixer.use_patch(self.patch_map[0])
        self.game.mixer.load_music('ocean_sounds.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1
        
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
                #self.game.lasers.turn_on(event.key)
            elif event.type == EventType.BUTTON_UP:
                self.check_for_clue_success()
                #print('button up:', event.key)
                #self.game.lasers.turn_off(event.key)

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                self.game.mixer.use_patch(self.patch_map[toggle_state])

        # this section/ style of trigger may be defunt (TODO)
        #if self.input_manager.changed_state:
        #    state = State(self.input_manager.state)
        #    action = self.match_triggers(state)
        #    action(state)

        # todo: set output state...

        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

    def default_action(self, state: 'State'):
        self.button_presssed(state)

ClueFinder()
