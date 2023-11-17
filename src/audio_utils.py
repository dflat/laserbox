from pygame.mixer import Sound
import pygame
import os
import time
import threading
from event_loop import SoundEndEvent
from config import PROJECT_ROOT

class Mixer:
    MUSIC_DIR = os.path.join(PROJECT_ROOT, 'assets', 'music')
    SOUNDS_DIR = os.path.join(PROJECT_ROOT, 'assets', 'sounds')
    PATCH_DIR = os.path.join(SOUNDS_DIR, 'patches')
    DUCK_DUR = .25
    VOL_LOW = .45
    VOL_HIGH = 1
    FPS = 30

    def __init__(self, sr=22050, bitdepth=-16, channels=2, buffer=2048):
        pygame.mixer.pre_init(sr, bitdepth, channels, buffer)
        pygame.mixer.init()

        ## testing this to get event loop to run smoothly w/out display output
        ## maybe do this in run.py or Game class...
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.init()
        pygame.display.set_mode((1,1))
        ##

        self.patch = None
        self.patches = { }
        self._load_patch('numbers')
        self.use_patch('numbers')
        self.fps = self.FPS

    def load_music(self, filename):
        path = os.path.join(self.MUSIC_DIR, filename)
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

    def play(self, sound):
        sound.play()

    def play_by_id(self, bank_id, duck=True):
        sound = self.patch[bank_id]
        self.duck_for_sound(sound) if duck else self.play(sound)

    def _init_sound_channel(self):
        self.sound_q = threading.Queue()
        self.q_remote = threading.Event()

    def async_duck(self, sound):
        def async_fade(start_vol, end_vol):
            pass
        # register as a waitier for sound's end_event
        evt = SoundEndEvent(sound)
        evt.set_done_callback(async_fade, self.VOL_LOW, self.VOL_HIGH)
            
    def duck_for_sound(self, sound):
        threading.Thread(target=self._duck_for_sound, args=(sound,)).start()

    def _duck_for_sound(self, sound):
        sound.play() # start playing sound just as fade down begins
        fade_dur = min(self.DUCK_DUR, sound.get_length()/2)
        self._fade(pygame.mixer.music.get_volume(), self.VOL_LOW, fade_dur)
        #sound.play()
        wait = sound.get_length() - fade_dur
        time.sleep(max(wait, 0))
        self._fade(pygame.mixer.music.get_volume(), self.VOL_HIGH, self.DUCK_DUR)

    def _fade(self, start_vol, end_vol, fade_dur, fps=30):
        t0 = time.time()
        while (t := time.time() - t0) < fade_dur:
            vol = lerp(t/fade_dur, start_vol, end_vol) 
            #print(f'vol: {vol:.2f}','t:', t)
            pygame.mixer.music.set_volume(vol)
            time.sleep(fade_dur/fps)
        pygame.mixer.music.set_volume(end_vol)

    def use_patch(self, patch_name):
        if patch_name not in self.patches:
            self._load_patch(patch_name)
        self.patch = self.patches[patch_name]

    def _load_patch(self, patch_name):
        """
        patch_name should be the name of the directory containing 14 wav files
            and placed in PATCH_DIR.
        Patch should be 14 wav files @ 22050 sr named 01.wav to 14.wav 
        """
        patch_path = os.path.join(self.PATCH_DIR, patch_name)
        patch = [Sound(f) for f in sorted(os.scandir(patch_path), key=lambda p:p.name)] 
        self.patches[patch_name] = patch
        
def lerp(t, a, b):
    return a + t*(b-a)

m = Mixer()

