"""MusicMaker: a free-play instrument where each button triggers a sound.

Each of the 14 buttons plays its sound from the active patch (held notes ring;
releasing fades them out) over a looping backing track. Useful as the simplest
example of the event-driven :meth:`Program.update` pattern.

Note:
    :meth:`MusicMaker.start` re-initialises ``pygame.mixer`` (it sets a specific
    config), which invalidates cached ``Sound`` objects. GameSelect re-establishes
    the mixer/effects when control returns to it.
"""
from .base import *
from ..event_loop import *
from ..config import config
import pygame
import os

class MusicMaker(Program):
    """Free-play instrument: button N plays sound N from the active patch."""

    def __init__(self):
        super().__init__()
        self.patch_map = {  0: 'Instruments_A_22050',
                        }

    def start(self):
        """Re-init the mixer, select the instrument patch, and loop the backing track."""
        sr=int(44100/2)
        bitdepth=-16
        channels=1
        buffer=config.AUDIO_BUFFER
        pygame.mixer.quit()
        pygame.mixer.init(sr, bitdepth, channels, buffer)
        print(f'mixer re-initialized by MusicMaker to sr:{sr}, buffer:{buffer}')
        self.game.mixer.use_patch(self.patch_map[0])
        self.game.mixer.load_effect('Instruments_A_BackingTrack_22050_mono.wav')
        self.game.mixer.play_effect('Instruments_A_BackingTrack_22050_mono.wav', loops=-1)
        self.game.mixer.set_music_volume(1)
        self.game.mixer.VOL_HIGH = 1

    def button_pressed(self, state: State):
        """Trigger placeholder (unused)."""
        pass

    def update(self, dt):
        """Play a note on button-down (rate-limited); fade it on button-up."""
        super().update(dt)
        # check event loop for input changes
        for event in events.get():
            if event.type == EventType.BUTTON_DOWN:
                if event.key not in self.cooldowns:
                    self.game.mixer.play_by_id(event.key, duck=False)
                    self.start_cooldown(event.key, ms=100)
            elif event.type == EventType.BUTTON_UP:
                self.game.mixer.fadeout_by_id(event.key, ms=200)

            elif isinstance(event, ToggleEvent):
                toggle_state = self.game.input_manager.state.toggles
                #self.game.mixer.use_patch(self.patch_map[toggle_state])

    def default_action(self, state: 'State'):
        """Fallback action: delegate to :meth:`button_pressed`."""
        self.button_presssed(state)

MusicMaker()
