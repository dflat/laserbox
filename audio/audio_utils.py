from pygame.mixer import Sound
import pygame

class Mixer:
    MUSIC_DIR = "../assets/music"
    SOUNDS_DIR = "../assets/sounds"
    PATCH_DIR = "../assets/sounds/patches"

    def __init__(self, sr=22050, bitdepth=-16, channels=2, buffer=2048):
        pygame.mixer.pre_init(sr, bitdepth, channels, buffer)
        pygame.mixer.init()
        self.patch = None
        self.patches = { }
        self._load_patch('numbers')
        self.use_patch('numbers')

    def use_patch(patch_name):
        if patch_name not in self.patches:
            self._load_patch(patch_name)
        self.patch = patch_name

    def _load_patch(self, patch_name):
        """
        patch_name should be the name of the directory containing 14 wav files
            and placed in PATCH_DIR.
        Patch should be 14 wav files @ 22050 sr named 01.wav to 14.wav 
        """
        patch_path = os.path.join(self.PATCH_DIR, patch_name)
        patch = [Sound(f) for f in sorted(os.scandir(patch_path))] 
        self.patches[patch_name] = patch
        
