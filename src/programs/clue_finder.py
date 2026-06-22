"""ClueFinder: spell a hidden "clue phrase" using buttons + toggle-selected banks.

Each toggle state selects a word bank (nouns/verbs/adverbs/numbers); pressing a
button speaks a word from the active bank. Entering the correct ordered sequence
of ``(button, toggle)`` pairs solves a clue. Solving every clue wins.
"""
from .base import *
from ..event_loop import *
from ..animation import Animation, ping_pong, random_k_dance
from ..config import config
from collections import deque
import os

class ClueFinder(Program):
    """Spell ordered ``(button, toggle)`` "clue phrases" to win.

    Toggles pick the active word bank (:attr:`patch_map`); buttons speak words
    from it. :attr:`clues` lists the target phrases.
    """

    def __init__(self):
        super().__init__()
        self.default_action = self.button_pressed
        self.triggers = {

        }
        self.sequence_triggers = { }
        self.patch_map = {  0: 'nouns',
                            1: 'verbs',
                            2: 'adverbs',
                            3: 'numbers'}

        self.clues = [((0,0),(7,1),(3,2),(6,0))] # (button_id, toggle_state [i.e. patch_map index])

    def clue_success(self):
        """Advance to the next clue; on the last, celebrate and stop input."""
        self.clue_idx += 1
        print(f'you found Clue Phrase # {self.clue_idx}!')
        if self.clue_idx >= len(self.clues):
            print(f'you found ALL the clues!')
            self.after(1000, self.celebrate)
            self.game.mixer.fade_music(2000)
            self.playing = False

    def celebrate(self):
        """Play the win sound + animation, then quit after it finishes."""
        self.game.mixer.play_effect(self.congrats_sound)
        self.success_anim.start()
        self.after(self.win_dur*1000, self.quit)

    def check_for_clue_success(self, clue_phrase_length=4, max_sequence_length=4):
        """Test recent button presses against the current clue phrase, in order.

        Args:
            clue_phrase_length: Number of words in the clue to match.
            max_sequence_length: How many recent BUTTON_DOWN events to consider.
        """
        print('seq:', clue_phrase_length, max_sequence_length)
        current_clue = self.clues[self.clue_idx]
        phrase_word_index = 0
        for e in events.get_filtered_history(EventType.BUTTON_DOWN, n=max_sequence_length):
            candidate_phrase_word = (e.key, e.state.toggles)
            target_phrase_word = current_clue[phrase_word_index]
            print('candidate:', candidate_phrase_word, 'target:', target_phrase_word)
            if candidate_phrase_word == target_phrase_word:
                phrase_word_index += 1
                print(f'got word {phrase_word_index} correct.')
            if phrase_word_index == (clue_phrase_length):
                self.clue_success()

    def quit(self):
        """Hand control back to the state machine."""
        # cleanup would happen here (nothing to cleanup?)
        super().quit()

    def start(self):
        """Select the initial word bank, loop ambience, and load win assets."""
        initial_toggle_state = self.game.input_manager.state.toggles
        self.game.mixer.use_patch(self.patch_map[initial_toggle_state])
        self.game.mixer.load_music('ocean_sounds22050.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1

        self.congrats_sound = os.path.join('positive', 'congrats_extended.wav')
        self.game.mixer.load_effect(self.congrats_sound, volume=config.CONGRATS_VOL)
        self.win_dur = self.game.mixer.effects[self.congrats_sound].get_length()
        self.success_anim = random_k_dance(k=3, fps=6, dur=self.win_dur - 1.2)

        self.playing = True
        self.clue_idx = 0
        self.button_down_history = deque(maxlen=100)

    def button_pressed(self, state: State):
        """Default trigger action: log the pressed state (debug)."""
        print('clue finder got:', state, int(state))


    def update(self, dt):
        """Speak a word on button-down; check the clue on button-up; swap bank on toggle."""
        super().update(dt)
        if not self.playing:
            return
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                if event.key not in self.cooldowns:
                    self.game.mixer.play_by_id(event.key)
                    toggle_state = self.game.input_manager.state.toggles
                    self.button_down_history.append((event.key, toggle_state))
                    self.start_cooldown(event.key, ms=250)
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
