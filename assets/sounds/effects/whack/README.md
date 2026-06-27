# Whack-a-Mole audio

Audio for `src/programs/whack_a_mole.py`. All wavs are **22050 Hz / mono / 16-bit
PCM** by repo convention.

## Sound effects (fixed clips)

| File                | Played when                                        |
|---------------------|----------------------------------------------------|
| `popup/pop-up.wav`  | a mole appears (laser lights)                      |
| `hits/hammer.wav`   | **every** button press (the mallet swing)          |
| `hits/mole-hit.wav` | only on a **successful** whack (a mole was lit)    |

So a hit you land plays *both* `hammer` and `mole-hit`; a swing at an empty hole
plays just `hammer`. If `mole-hit.wav` is ever missing the game falls back to the
pitched `kicks_ascending_mono` patch so a hit always makes a sound.

Paths are set in `config.WhackAMole` (`POPUP` / `HAMMER` / `MOLE_HIT`). Keep clips
short — `hammer` fires on every press, so a long clip would pile up across
pygame's mixer channels. The committed clips were trimmed to ~0.5 s and converted
to the repo convention (the source files were 9.7 s / 44.1 kHz / stereo / 24-bit).

## Spoken voice-over (recorded)

Generated with the project voice `en-AU-WilliamMultilingualNeural` (edge-tts) and
converted to the repo convention. The game still loads them defensively, so
deleting any one degrades gracefully (it's skipped). `welcome.wav` is played on
entry and is **skippable** — pressing a button to pick a mode cuts it short.

| File                                  | Line                                          |
|---------------------------------------|-----------------------------------------------|
| `welcome.wav`                         | *intro + rules + "press a black button for one player… white button for two"* |
| `result_single.wav`                   | "Time's up! Nice whacking."                   |
| `player_1_wins.wav`                   | "Player one wins! The black side takes it."   |
| `player_2_wins.wav`                   | "Player two wins! The white side takes it."   |
| `tie.wav`                             | "It's a tie! Dead even."                      |
| `../menu/whack_a_mole.wav`            | "Whack a mole." (GameSelect menu announcement)|

To re-record a line (per `CLAUDE.md`):

```bash
edge-tts --voice en-AU-WilliamMultilingualNeural \
  --text "Time's up! Nice whacking." --write-media /tmp/x.mp3
ffmpeg -y -i /tmp/x.mp3 -ar 22050 -ac 1 -sample_fmt s16 \
  assets/sounds/effects/whack/result_single.wav
```
