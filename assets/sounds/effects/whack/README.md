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
| `you_hit.wav`                         | "You hit" (1-player hit readout lead-in)       |
| `player_1_hit.wav`                    | "Player one hit" (2-player readout lead-in)    |
| `player_2_hit.wav`                    | "Player two hit" (2-player readout lead-in)    |
| `mole.wav` / `moles.wav`              | "mole" / "moles" (suffix after the hit count)  |
| `and_got.wav`                         | "and got" (joins the hit count to the miss count) |
| `miss.wav` / `misses.wav`             | "miss" / "misses" (suffix after the miss count) |
| `../menu/whack_a_mole.wav`            | "Whack a mole." (GameSelect menu announcement)|

## Spoken result readout (every round)

Every round ends by speaking, per player, **"<who> hit N mole(s) and got M
miss(es)"**. Each count is **composed** from the `num/` bank (the same idea as
Trivia's score line, which sequences number clips): ones/teens `num/0…19.wav`,
tens `num/20,30,…,90.wav`, and hundreds `num/100.wav`/`num/200.wav`. Any value
**0-299** is up to three clips — e.g. 247 → `num/200` + `num/40` + `num/7` (see
`WhackAMole._number_clips`); counts above 299 are clamped.

A **miss** is a mole that timed out unwhacked (tracked per half). The hit count
takes `mole`/`moles` and the miss count `miss`/`misses` (singular only at exactly
one); the miss half is always spoken, so a shutout reads "…and got **zero**
misses".

* 1-player: `result_single` → *hits* → *misses* → (`new_highscore` if a PB).
* 2-player: *hits(P1)* → *misses(P1)* → *hits(P2)* → *misses(P2)* → winner → (`new_record`).

  where *hits* = `you_hit`/`player_N_hit` → *count* → `mole`/`moles`, and
  *misses* = `and_got` → *count* → `miss`/`misses`.

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
