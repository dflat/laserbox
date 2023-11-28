from .base import *
from ..event_loop import *
from ..animation import Animation, ping_pong, random_k_dance
from ..config import config

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

        self.clues = [((0,0),(1,1),(0,2)),
                        ((0,0),(1,1),(0,2)),
                        ((0,0),(1,1),(0,2)),
                      ((2,3),(2,2),(2,1))] # (button_id, toggle_state [i.e. patch_map index])
        self.clue_idx = 0

    def clue_success(self):
        # todo : self.game.lasers.dance()
        self.clue_idx += 1
        print(f'you found Clue Phrase # {self.clue_idx}!')
        self.success_anim.start()
        if self.clue_idx >= len(self.clues):
            print(f'you found ALL the clues!')
            # todo: revert control of game back to state machine, or something
        
    def check_for_clue_success(self, clue_phrase_length=3, max_sequence_length=3):
        current_clue = self.clues[self.clue_idx]
        phrase_word_index = 0
        for e in events.get_filtered_history(EventType.BUTTON_DOWN, n=max_sequence_length):
            candidate_phrase_word = (e.key, e.state.toggles)
            target_phrase_word = current_clue[phrase_word_index]
            #print('candidate:', candidate_phrase_word, 'target:', target_phrase_word)
            if candidate_phrase_word == target_phrase_word:
                phrase_word_index += 1
                #print(f'got word {phrase_word_index} correct.')
            if phrase_word_index == (clue_phrase_length):
                self.clue_success()



    def start(self):
        #print('cluefinder starting...')
        self.game.mixer.use_patch(self.patch_map[0])
        self.game.mixer.load_music('ocean_sounds22050.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1
        self.cooldown_ticks = int(config.FPS*1)
        #self.success_anim = ping_pong(fps=5, loops=3) #Animation(dur=2000, loops=3)
        self.success_anim = random_k_dance(k=3, fps=5, dur=10) #Animation(dur=2000, loops=3)
        self.cooldowns = { } # button id => tick when triggered
        self.tick = 0
        
    def button_pressed(self, state: State):
        print('clue finder got:', state, int(state))

    def check_cooldowns(self):
        to_free = []
        for button_id, start_tick in self.cooldowns.items():
            if self.tick - start_tick > self.cooldown_ticks:
                to_free.append(button_id)
        for button_id in to_free:
            self.cooldowns.pop(button_id)

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        self.tick += 1
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                if event.key not in self.cooldowns:
                    self.game.mixer.play_by_id(event.key)
            elif event.type == EventType.BUTTON_UP:
                self.check_for_clue_success()

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                print('toggles:', toggle_state)
                self.game.mixer.use_patch(self.patch_map[toggle_state])

        # this section/ style of trigger may be defunt (TODO)
        #if self.input_manager.changed_state:
        #    state = State(self.input_manager.state)
        #    action = self.match_triggers(state)
        #    action(state)

        # todo: set output state...

        #sequence_action = self.match_sequence_triggers(maxlen=3)
        

ClueFinder()
