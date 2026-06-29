"""Audio playback: the :class:`Mixer` wrapper around ``pygame.mixer``.

Three kinds of audio:

* **music** -- a single streamed track (looping background), via
  ``pygame.mixer.music``.
* **effects** -- one-shot ``Sound`` objects loaded from
  ``assets/sounds/effects`` (subdirs allowed, e.g. ``"positive/hooray.wav"``).
* **patches** -- a "bank" of 14 ``Sound`` objects (one per button) loaded from a
  directory under ``assets/sounds/patches``; played by index with
  :meth:`Mixer.play_by_id`.

All assets are 22050 Hz / mono / 16-bit by convention. The mixer also supports
"ducking" -- briefly lowering the music while a voice clip plays.
"""
from pygame.mixer import Sound
import pygame
import os
import subprocess
import time
from . import clock
import threading
from .config import config
from .event_loop import SoundEndEvent, events


#class GameChannel(pygame.mixer.Channel):
    # WIP
#    def set_endevent(self, pg_evt_type):
#        super().set_endevent(pg_evt_type)
#        events.put(SoundEndEvent()) # not here..look in source for when event is pushed
#        print('set endevent for channel')


class Mixer:
    """Loads and plays music, one-shot effects, and 14-sound patches.

    Args:
        sr: Sample rate (Hz).
        bitdepth: pygame format code (negative = signed); -16 = signed 16-bit.
        channels: 1 = mono.
        buffer: Mixer buffer size in samples (lower = lower latency).

    Class Attributes:
        MUSIC_DIR / SOUNDS_DIR / PATCH_DIR / EFFECTS_DIR (str): Asset roots.
        DUCK_DUR (float): Duck fade duration (seconds).
        VOL_LOW / VOL_HIGH (float): Ducked / normal music volumes.
    """
    MUSIC_DIR = os.path.join(config.PROJECT_ROOT, 'assets', 'music')
    SOUNDS_DIR = os.path.join(config.PROJECT_ROOT, 'assets', 'sounds')
    PATCH_DIR = os.path.join(SOUNDS_DIR, 'patches')
    EFFECTS_DIR = os.path.join(SOUNDS_DIR, 'effects')
    DUCK_DUR = .25
    VOL_LOW = .15
    VOL_HIGH = 1
    FPS = 30

    def __init__(self, sr=int(22050), bitdepth=-16, channels=1, buffer=config.AUDIO_BUFFER):
        pygame.mixer.pre_init(sr, bitdepth, channels, buffer)
        pygame.mixer.init()
        print(f'mixer initialized in Mixer class to sr:{sr}, buffer:{buffer}')

        self.patch = None
        self.patches = { }
        self.effects = { }
        self._load_patch('numbers')
        self.use_patch('numbers')
        self.fps = self.FPS

    def load_music(self, filename, loops=-1, fade_ms=0):
        """Load a music track from ``MUSIC_DIR`` and start playing it.

        Args:
            filename: File name under ``assets/music``.
            loops: -1 loops forever; 0 plays once.
            fade_ms: Fade-in time in milliseconds.
        """
        path = os.path.join(self.MUSIC_DIR, filename)
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)

    def fade_music(self, fade_ms=0):
        """Fade the music out over ``fade_ms`` milliseconds."""
        pygame.mixer.music.fadeout(fade_ms)

    def music_length(self, filename):
        """Return the duration (seconds) of a track in ``MUSIC_DIR``.

        ``pygame.mixer.music`` exposes no length, so this loads the file as a
        ``Sound`` purely to measure it (the bytes are discarded). Used when a
        track's own length needs to drive timing -- e.g. Trivia's thinking song
        doubling as the answer clock.

        Args:
            filename: File name under ``assets/music``.

        Returns:
            float | None: Length in seconds, or ``None`` if it can't be read.
        """
        path = os.path.join(self.MUSIC_DIR, filename)
        try:
            return Sound(path).get_length()
        except Exception as e:  # pragma: no cover - missing/unsupported file
            print(f"[Mixer] could not measure {filename!r}: {e}")
            return None

    def stop_all(self):
        """Stop the music stream and every playing effect channel at once."""
        pygame.mixer.music.stop()
        pygame.mixer.stop()

    def play_effect(self, filename, loops=0):
        """Play a one-shot effect, loading it on first use.

        Args:
            filename: Path under ``assets/sounds/effects`` (subdirs allowed).
            loops: Extra repeats after the first play (-1 loops forever).
        """
        if filename not in self.effects:
            self.load_effect(filename)
        self.effects[filename].play(loops=loops)

    def load_effect(self, filename, volume=1):
        """Load (or reload) an effect into the cache at the given volume."""
        path = os.path.join(self.EFFECTS_DIR, filename)
        sound = Sound(path)
        sound.set_volume(volume)
        self.effects[filename] = sound

    def set_music_volume(self, vol):
        """Set the music stream volume (0..1)."""
        pygame.mixer.music.set_volume(vol)

    def aplay(self, path):
        """Play a file via the external ``aplay`` command (blocking)."""
        subprocess.run(f"aplay {path}", shell=True)

    def play(self, sound):
        """Play a pygame ``Sound`` object directly."""
        sound.play()

    def play_by_id(self, bank_id, duck=True):
        """Play sound ``bank_id`` from the current patch.

        Args:
            bank_id: Index (0..13) into the active patch.
            duck: If True, duck the music for the duration of the sound.
        """
        sound = self.patch[bank_id]
        self.duck_for_sound(sound) if duck else self.play(sound)

    def fadeout_by_id(self, bank_id, ms=100):
        """Fade out sound ``bank_id`` of the current patch over ``ms`` ms."""
        self.patch[bank_id].fadeout(ms)

    def _init_sound_channel(self):
        self.sound_q = threading.Queue()
        self.q_remote = threading.Event()

    def async_duck(self, sound):
        """WIP: register an end-of-sound callback to restore volume (unused)."""
        def async_fade(start_vol, end_vol):
            pass
        # register as a waitier for sound's end_event
        evt = SoundEndEvent(sound)
        evt.set_done_callback(async_fade, self.VOL_LOW, self.VOL_HIGH)

    def duck_for_sound(self, sound):
        """Play ``sound`` while ducking the music, on a background thread."""
        threading.Thread(target=self._duck_for_sound, args=(sound,)).start()

    def _duck_for_sound(self, sound):
        """Worker: play the sound, then duck the music for its duration."""
        sound.play() # start playing sound just as fade down begins
        self._duck_music(sound.get_length())

    def duck_music(self, duration, duck_vol=None, restore_vol=None):
        """Dip the music for ``duration`` seconds, then restore it (threaded).

        Like :meth:`duck_for_sound` but it does **not** own the sound: the caller
        plays its own effect (e.g. via :meth:`play_effect`) and this only rides
        the music volume down and back. That lets a program whose bed sits below
        full volume duck under a cue and return to *its* level, not ``VOL_HIGH``.

        Args:
            duration: Seconds to stay ducked (typically the cue's length).
            duck_vol: Volume to dip to. Defaults to :attr:`VOL_LOW`.
            restore_vol: Volume to return to. Defaults to :attr:`VOL_HIGH`.
        """
        threading.Thread(target=self._duck_music,
                         args=(duration, duck_vol, restore_vol)).start()

    def _duck_music(self, duration, duck_vol=None, restore_vol=None):
        """Worker: fade the music down, hold for ``duration``, fade back up."""
        duck_vol = self.VOL_LOW if duck_vol is None else duck_vol
        restore_vol = self.VOL_HIGH if restore_vol is None else restore_vol
        fade_dur = min(self.DUCK_DUR, duration / 2)
        self._fade(pygame.mixer.music.get_volume(), duck_vol, fade_dur)
        time.sleep(max(duration - fade_dur, 0))
        self._fade(pygame.mixer.music.get_volume(), restore_vol, self.DUCK_DUR)

    def _fade(self, start_vol, end_vol, fade_dur, fps=30):
        """Linearly ramp the music volume from ``start_vol`` to ``end_vol``."""
        t0 = clock.monotonic()
        while (t := clock.monotonic() - t0) < fade_dur:
            vol = lerp(t/fade_dur, start_vol, end_vol)
            #print(f'vol: {vol:.2f}','t:', t)
            pygame.mixer.music.set_volume(vol)
            time.sleep(fade_dur/fps)
        pygame.mixer.music.set_volume(end_vol)

    def use_patch(self, patch_name, volume=1):
        """Make ``patch_name`` the active patch, loading it on first use."""
        if patch_name not in self.patches:
            self._load_patch(patch_name, volume)
        self.patch = self.patches[patch_name]

    def _load_patch(self, patch_name, volume=1):
        """Load a 14-sound patch directory into the cache.

        Args:
            patch_name: Directory name under ``PATCH_DIR`` containing 14 wav
                files (22050 Hz), named so that sorting yields button order.
            volume: Volume applied to every sound in the patch.
        """
        patch_path = os.path.join(self.PATCH_DIR, patch_name)
        patch = [Sound(f.path) for f in sorted(os.scandir(patch_path), key=lambda p:p.name)]
        for sound in patch:
            sound.set_volume(volume)
        self.patches[patch_name] = patch

#import simpleaudio as sa
class SimpleMixer(Mixer):
    """Experimental ``simpleaudio`` backend variant (not currently wired up)."""

    def __init__(self, sr=int(22050), bitdepth=-16, channels=1, buffer=config.AUDIO_BUFFER):
        self.sr = sr
        self.channels = channels
        self.bytes_per_sample = int(abs(bitdepth)/2)
        self.patch = None
        self.patches = { }
        self._load_patch('numbers')
        self.use_patch('numbers')
        self.fps = self.FPS

    def _load_patch(self, patch_name):
        patch_path = os.path.join(self.PATCH_DIR, patch_name)
        patch = [sa.WaveObject.from_wave_file(f.path)
                 for f in sorted(os.scandir(patch_path), key=lambda p:p.name)]
        self.patches[patch_name] = patch


def lerp(t, a, b):
    """Linear interpolation: return ``a`` at ``t=0`` and ``b`` at ``t=1``."""
    return a + t*(b-a)
