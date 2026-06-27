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
| `new_highscore.wav`                   | "New high score! You're the top whacker on the box!" (solo personal best beaten) |
| `new_record.wav`                      | "A new record! …" (2-player all-time best beaten) |
| `you_scored.wav`                      | "You scored" (1-player score readout lead-in)  |
| `player_1_scored.wav`                 | "Player one scored" (2-player readout lead-in) |
| `player_2_scored.wav`                 | "Player two scored" (2-player readout lead-in) |
| `../menu/whack_a_mole.wav`            | "Whack a mole." (GameSelect menu announcement)|

## Spoken score readout (every round)

Every round ends by speaking the score. The number is **composed** from a small
bank in `num/` (the same idea as Trivia's score line, which sequences number
clips): `num/0.wav … num/19.wav` plus the tens `num/20.wav, 30, …, 90`. Any value
0-99 is one or two clips — e.g. 47 → `num/40.wav` + `num/7.wav` (see
`WhackAMole._number_clips`). Scores are clamped to 0-99.

* 1-player: `result_single` → `you_scored` → *number* → (`new_highscore` if a PB).
* 2-player: `player_1_scored` → *N* → `player_2_scored` → *M* → winner → (`new_record`).

## Score tracker

A persistent high-score file lives at `state/whack_a_mole.json` (repo-relative,
**gitignored** — each physical box keeps its own records). It holds `solo_best`
(1-player personal best) and `versus_best` (highest single-side score in a
2-player round). When a round beats the relevant record, the game saves it and
plays the fanfare above (and 1-player adds a bigger laser dance). Path is set by
`config.WhackAMole.HIGHSCORE_PATH`.

To re-record a line (per `CLAUDE.md`):

```bash
edge-tts --voice en-AU-WilliamMultilingualNeural \
  --text "Time's up! Nice whacking." --write-media /tmp/x.mp3
ffmpeg -y -i /tmp/x.mp3 -ar 22050 -ac 1 -sample_fmt s16 \
  assets/sounds/effects/whack/result_single.wav
```
