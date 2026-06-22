# Audio

All sound goes through {class}`src.audio_utils.Mixer` (a thin wrapper over
`pygame.mixer`), accessed as `self.game.mixer` inside a program.

## Three kinds of sound

| Kind | Source dir | API | Notes |
|------|-----------|-----|-------|
| **music** | `assets/music` | `load_music(name, loops=-1)`, `fade_music(ms)`, `set_music_volume(v)` | one streamed track (looping background) |
| **effects** | `assets/sounds/effects` | `load_effect(name, volume)`, `play_effect(name)` | one-shot `Sound`s; subdirs allowed (`"positive/hooray.wav"`) |
| **patches** | `assets/sounds/patches` | `use_patch(name)`, `play_by_id(i)` | a bank of 14 sounds, one per button |

A **patch** is a directory of 14 wavs whose sorted order is button order
(`numbers`, `nouns`, `kicks_ascending_mono`, …). `play_by_id(i)` plays the i-th.

## Asset convention

Everything is **22050 Hz / mono / 16-bit PCM WAV**. Keep new assets in that
format so they mix without resampling.

To generate spoken lines (used by the GameSelect menu) with `edge-tts`:

```bash
edge-tts -v en-AU-WilliamMultilingualNeural -t "Choose a game!" --write-media /tmp/x.mp3
ffmpeg -i /tmp/x.mp3 -ar 22050 -ac 1 -y assets/sounds/effects/menu/choose_a_game.wav
```

```{note}
`assets/` is gitignored — audio is managed outside the repo. Generated files
live on disk but are not committed.
```

## Ducking

For voice clips over music, {meth}`Mixer.play_by_id <src.audio_utils.Mixer.play_by_id>`
with `duck=True` (the default) briefly fades the music down for the clip's
duration and back up afterward. This runs on a short-lived background thread
({meth}`~src.audio_utils.Mixer.duck_for_sound`) so it doesn't block the loop.
Pass `duck=False` for rapid-fire sounds (e.g. an instrument) where ducking would
thrash the volume.

## Stopping everything

{meth}`Mixer.stop_all <src.audio_utils.Mixer.stop_all>` stops the music stream
and all effect channels at once. The state machine calls it on every program
switch, so you rarely call it yourself.

## Sample-rate / re-init gotcha

{class}`~src.programs.music_maker.MusicMaker` calls `pygame.mixer.quit()` +
`init()` in its `start()` to set a specific config. That invalidates previously
loaded `Sound` objects. The takeaways:

- Load the effects/patches you need in your program's `start()` (not once in
  `__init__`), so they are valid against the current mixer.
- GameSelect re-establishes a standard mixer and reloads its own effects on
  entry, so returning from MusicMaker is clean.
