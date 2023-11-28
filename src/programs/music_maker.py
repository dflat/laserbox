from .base import *
from ..event_loop import *
import pygame
import os

class MusicMaker(Program):
    def __init__(self):
        super().__init__()
        self.patch_map = {  0: 'Instruments_A',
                        }

    def start(self):
        sr=int(44100/2)
        bitdepth=-16
        channels=1
        buffer=int(2048//4)
        pygame.mixer.quit()
        pygame.mixer.init(sr, bitdepth, channels, buffer)
        print(f'mixer re-initialized by MusicMaker to sr:{sr}, buffer:{buffer}')
        self.game.mixer.use_patch(self.patch_map[0])
        self.game.mixer.load_effect('Instruments_A_BackingTrack.wav')
        self.game.mixer.play_effect('Instruments_A_BackingTrack.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1
        
    def button_pressed(self, state: State):
        pass

    def update(self, dt):
        """
        Called every frame, whether state has changed or not.
        """
        super().update(dt)
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                self.game.mixer.play_by_id(event.key, duck=False)
            elif event.type == EventType.BUTTON_UP:
                self.game.mixer.fadeout_by_id(event.key, ms=200)

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                #self.game.mixer.use_patch(self.patch_map[toggle_state])

    def default_action(self, state: 'State'):
        self.button_presssed(state)

MusicMaker()
