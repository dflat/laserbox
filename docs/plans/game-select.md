# Plan: GameSelect meta-program

- **Status:** approved, in progress
- **Date:** 2026-06-21
- **Author:** rjr (design) + Claude (drafting)

## 1. Goal

Add a `GameSelect` meta-program: an operator-facing selection menu, reachable
via a special input gesture **from any running program**, that announces
"Choose A Game!" and lets the operator assign each of the 14 buttons to a game
or a pre-made composition (Composer). First press of a button announces the
entry's name; a second press of the same button launches it. When a launched
game (or composition) finishes, control returns to GameSelect.

GameSelect becomes the system "home": the box boots into it, and every launched
context returns to it on completion.

## 2. Design decisions

These were resolved by walking the full design tree. Each is locked.

### 2.1 Lifecycle — hub model (Model A)
- Boot goes straight into GameSelect.
- Picking a **single program** runs it once; on finish, return to GameSelect.
- Picking a **Composer** runs the whole sequence; on finish, return to GameSelect.
- Single-program and composer launches are unified under one "context" concept
  (a single program = a one-item context). GameSelect is the only thing that
  *creates* a new context.

### 2.2 Entry gesture detection — global, non-consuming
- Detected at the **`StateMachine` level** (not per-program), each frame, before
  the active program updates. It reads input *state* (non-consuming), so it is
  immune to how the active program drains the event queue.
- Fires **mid-game** as a true interrupt.
- **Ignored while already inside GameSelect** (re-doing the gesture does not stack).

### 2.3 The gesture itself
- Hold buttons **0 & 1** simultaneously, and while both are held, toggle-0
  **changes state twice** — i.e. `on→off→on` *or* `off→on→off` (it returns to
  its starting state). Both buttons must stay held across both transitions;
  releasing either resets the detector.
- **Mask-based match:** only the bits for buttons 0, 1 and toggle-0 are
  considered; all other input bits are ignored, so the gesture works regardless
  of what else is on (context-independent).
- The pair, toggle index, and required transition count are configurable.

### 2.4 Interrupt handling — abandon + hard teardown
- The interrupted program is **abandoned**, not paused/resumed (the half-built
  `PAUSED` path is dropped as out of scope).
- Teardown must: stop/fade music and any playing effects, kill all running
  animations and clear the laser word, and **flush the program's pending
  `scheduler` and `cooldowns`** so stale callbacks don't leak into GameSelect or
  the next game.
- **`scheduler`/`cooldowns` refactored from shared class attributes to
  per-instance**, since they were never meant to be shared (a latent bug that
  mid-game interrupts would otherwise expose).

### 2.5 Boot / launch model
- Boot enters GameSelect instead of auto-starting `BirthdayComposer`.
  `BirthdayComposer` is demoted to a selectable menu entry (and will later be
  replaced by a new composition).
- `StateMachine`'s single `self.composer` is generalized into a current
  **context**. `swap_program()` advances the current context; when the context
  is exhausted it returns to GameSelect rather than indexing past the end.
- The `-p ProgramName` CLI flag is preserved for dev (launch one game directly).

### 2.6 Menu map
- `config.GameSelect.MENU = {button_id: (launch_target, announcement_file)}`.
- `launch_target` resolves to either a Program class name or a Composer class name.
- Default map:

  | Button | Entry                         |
  |--------|-------------------------------|
  | 0      | Golf                          |
  | 1      | Flipper                       |
  | 2      | ClueFinder                    |
  | 3      | MusicMaker                    |
  | 4      | BirthdayComposer (sequence)   |
  | 5–13   | unassigned                    |

- `TogglePattern` is excluded as a standalone entry (it's a between-games clue
  gate that needs args). `Trivia`/`SystemSettings` are empty stubs.
- Unassigned button → **no-op**.

### 2.7 Selection UX
- Last-pressed assigned button is the "armed" selection. First press announces;
  pressing the same button again launches; pressing a different assigned button
  re-arms and announces the new one.
- **Arm timeout: 10s** (configurable). If no second press occurs within the
  window, the arm clears (a later press only re-announces).
- **Laser feedback:** while a button is armed, light *that button's laser*
  (others off).
- "Choose A Game!" plays once on entry.
- **No cancel/exit** — since entering GameSelect abandons the prior context,
  there's nothing to return to; the operator leaves only by launching something.

### 2.8 Audio
- Voice: `en-AU-WilliamMultilingualNeural`.
- Pipeline: `edge-tts -v <voice> -t "<text>" --write-media /tmp/x.mp3`
  then `ffmpeg -i /tmp/x.mp3 -ar 22050 -ac 1 -y <out>.wav` (matches the
  existing 22050 Hz / mono / 16-bit convention).
- Stored in `assets/sounds/effects/menu/`, loaded as effects (`menu/golf.wav`, …).
- Lines: `choose_a_game.wav` ("Choose A Game!"), `golf.wav`, `flipper.wav`,
  `clue_finder.wav` ("Clue Finder"), `music_maker.wav` ("Music Maker"),
  `birthday.wav` ("Birthday").
- `MusicMaker.start()` calls `pygame.mixer.quit()` + re-`init()`, invalidating
  previously loaded `Sound` objects; therefore GameSelect **(re)loads its
  announcement effects in `start()` every time it is entered** and ensures the
  mixer is at the standard config.

## 3. Implementation phases

### Phase 1 — Control-flow + teardown groundwork (`src/programs/base.py`)
- Make `scheduler`, `cooldowns`, `schedule_id` per-instance.
- Add `Program.teardown()` (clear this program's scheduler + cooldowns).
- Generalize `StateMachine`:
  - Add `COMPOSER_CLASSES` registry (name → class); keep `PROGRAMS`.
  - Replace `self.composer` with `self.context`; `swap_program()` advances the
    context and returns to GameSelect when exhausted.
  - Add `enter_game_select()` (teardown → stop audio → `Animation.kill_all()` →
    clear lasers → activate + `start()` GameSelect).
  - Add `launch_context(target)` (resolve to one-item context or composer; set
    and swap to first program).
  - Add `check_system_triggers()` called at top of `update()` (skipped when the
    active program is GameSelect).
- Boot: `Game.__init__` calls `enter_game_select()` (keep `-p` path).

### Phase 2 — Gesture detector
- A `GestureDetector` fed the new `State` on each `changed_state`: tracks
  "buttons 0 & 1 both held" and counts toggle-0 transitions while continuously
  held; fires after 2 transitions; resets on button release. Params from config.

### Phase 3 — Animation teardown (`src/animation.py`)
- Add `Animation.kill_all()`; fix the stale `self` reference in `kill_by_id`.

### Phase 4 — GameSelect program (`src/programs/game_select.py`)
- `start()`: ensure mixer standard config; (re)load `menu/` effects; reset arm;
  clear lasers; play `choose_a_game.wav`.
- `update()`: on `BUTTON_DOWN` of an assigned button → launch if armed, else arm
  + announce + light laser + (re)start timeout. Unassigned → no-op. Expire arm
  on timeout.

### Phase 5 — Config (`src/config.py`)
- `class GameSelect`: `MENU`, `ARM_TIMEOUT_MS = 10000`, `TRIGGER_BUTTONS = [0,1]`,
  `TRIGGER_TOGGLE = 0`, `TRIGGER_TRANSITIONS = 2`.

### Phase 6 — Register `BirthdayComposer` in `COMPOSER_CLASSES`.

### Phase 7 — Audio assets
- Generate the WAVs per §2.8 (verify voice via `edge-tts -l`; needs network).

### Phase 8 — Simulator smoke test (`-s`)
- Boot→menu; gesture from inside a running game (hold keys `0`+`1`, toggle `e`);
  announce-then-launch; return-to-menu on finish; teardown leaves no stale
  audio/animation/scheduled callbacks. Use `grim` for screenshots if helpful.

## 4. Risks / notes
- Per-instance `scheduler`/`cooldowns` touches the `Program` base; confirmed no
  program relies on them being shared.
- Composer `finish()` currently dead-ends; the new `swap_program` treats an
  exhausted context as the go-home signal, routing all composers to GameSelect.
- edge-tts needs network; if unavailable, stop and flag rather than ship silent
  placeholder files.

## 5. Phase 9 (secondary project) — System documentation

After the GameSelect feature is confirmed robust and working, write
comprehensive onboarding documentation for the **whole** laserbox system (not
just GameSelect), targeted at a new developer who needs to understand and
contribute.

### Goals
- Readable at a high level (architecture, mental model, data/flow) **and**
  detailed enough that an engineer knows the specifics (per-module/class/method
  contracts).
- Browseable as HTML, using a standard Python documentation toolchain.

### Tooling
- **Sphinx** with:
  - **MyST-Parser** (author narrative pages in Markdown),
  - **autodoc** (pull API reference straight from source docstrings),
  - **napoleon** (Google-style docstrings).
- Output: HTML site under `docs/dev/` (Sphinx project in `docs/dev/`, built to
  `docs/dev/_build/html`).
- Adopt **Google-style docstrings** as the project convention and backfill them
  across modules as part of this phase.

### Proposed structure (`docs/dev/`)
- `index` — what laserbox is, hardware overview, how to run (Pi vs simulator).
- `architecture` — the frame loop, input→event→program→output pipeline, the
  fixed-timestep clock, the shift-register I/O model, the audio mixer model.
- `state-machine` — `State`/`StateSequence`, `StateMachine`, `Composer`/context
  model, `Program` lifecycle, the system-trigger / GameSelect path.
- `writing-a-program` — step-by-step guide to adding a new mini-game (the
  `Program` contract, events, scheduling, cooldowns, animations, audio).
- `animation` — `Frame`/`FrameSequence`/`Animation` and the factories.
- `audio` — patches vs effects vs music, ducking, sample-rate gotchas
  (MusicMaker re-init), asset conventions + TTS generation.
- `simulator` — how the dummy registers + keyboard mapping work, dev workflow.
- `hardware` — wiring, the 74HC595/74HC165 registers, pin map, GPIO guard.
- `api/` — autodoc API reference for every module.

### Note for implementers
Keep this phase in mind while building GameSelect: write Google-style
docstrings on new/changed code so the eventual autodoc pass has real content to
surface.
