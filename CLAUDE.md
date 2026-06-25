# CLAUDE.md

Guidance for AI agents working in this repo. For the human-facing overview, LFS
mental model, and full deploy story, see `README.md` and `docs/` — this file is
the operational cheat-sheet and the project assumptions that aren't obvious from
the code.

## What this is

Laserbox is firmware for a physical **laser-arcade box**: a player stands at one
unit with **14 buttons + 2 toggle switches** and **14 laser ports**, driven by a
Raspberry Pi through two shift registers (74HC165 in, 74HC595 out). It's a
**reusable multi-game platform**, not a single game: each mini-game is a
`Program`, and a `Composer` scripts an ordered run of programs. `GameSelect` is
the home menu the box boots into and returns to.

Input is one **16-bit word** per frame: low 14 bits = buttons, top 2 bits =
toggles. Lasers are a 14-bit output word. See `docs/dev/architecture.md` and
`docs/dev/authoring-programs.md` before making structural changes.

## Running & testing locally

- Use the project virtualenv: **`.venv/bin/python`**. The system `python3` does
  **not** have `pygame` — running with it will fail at import.
- Simulator (no hardware): `.venv/bin/python -m src -s`. Keyboard maps keys
  `0`-`9`,`a`-`f` to the 16 input bits (`c` = button 12, `d` = button 13,
  `e` = toggle 0, `f` = toggle 1).
- Launch a single program directly: `-p ProgramName`.
- Headless logic tests live in `scratch/` and need the dummy SDL drivers, e.g.:
  ```bash
  SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy .venv/bin/python scratch/test_gameselect.py
  ```
  These drive a real `Game` with a scripted input register and assert program
  transitions — prefer extending them over ad-hoc manual checks.

## Code conventions

- Every `Program` subclass lives in `src/programs/`, subclasses
  `programs.base.Program`, and **registers itself by being instantiated once at
  the bottom of its module**. `config.py` holds tunables (per-program nested
  classes like `config.GameSelect`).
- Keep **Google-style docstrings** on public classes/functions — Sphinx autodoc
  (`docs/dev/`) depends on them.
- Off-Pi/simulator code paths are gated on `'-s' in sys.argv` (and
  `sys.platform`); anything hardware- or system-destructive (GPIO, reboot,
  shutdown) must be a no-op under `-s` so it can't fire on a dev machine.
- Commits use Conventional Commits (`feat(Scope): …`); land features on a branch
  and merge to `main`.

## Interacting with the production Pi (remote)

The box runs on a Raspberry Pi (hostname `rzero`, user `pi`, passwordless sudo).

- **SSH: try `ssh box-ether` first** (hard-wired ethernet, more reliable). **Fall
  back to `ssh box`** when the box is only on Wi-Fi (ethernet unplugged / not
  routable). Both are aliases in `~/.ssh/config` for the same Pi.
- Repo on the Pi: `/home/pi/electronics/laserbox` (tracks `main`).
- The app **auto-starts at boot** as a **systemd _user_ service** named
  `laserbox` (linger enabled). Manage it over SSH with the user manager — these
  need `XDG_RUNTIME_DIR` set:
  ```bash
  XDG_RUNTIME_DIR=/run/user/1000 systemctl --user {status,restart,stop} laserbox
  XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -u laserbox -f
  ```
- **Deploy after merging to `main`:**
  ```bash
  cd ~/electronics/laserbox && git pull   # desktop must be ON for LFS
  XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart laserbox
  ```
  `git pull` alone also fetches the LFS blobs: the Pi has a standard
  `git lfs install` (active smudge filter + `post-merge` hook), so updated
  `.wav`s come down as real audio, not pointers — no separate `git lfs pull`
  needed. Because `filter.lfs.required = true`, if the desktop (Forgejo) is
  **off** the `git pull` itself **errors out** rather than silently leaving
  pointers, so a clean pull means the assets are present.

  A `git pull` updates files on disk but **does not reload the running process** —
  always restart the service to pick up new code (verify the `MainPID`/start time
  actually changed).

## Audio assets

- All audio is `assets/**/*.wav` tracked via **Git LFS** (pointers on GitHub
  `origin`, blobs on a self-hosted **Forgejo** at `192.168.1.246:3000`; the
  desktop must be powered on for any `lfs pull/push`). First LFS fetch on a new
  machine prompts for the Forgejo token (username `rjr`) — **never commit that
  token**. Full mental model is in `README.md`.
- **Generate new speech samples with `edge-tts`**, using the project voice
  **`en-AU-WilliamMultilingualNeural`** (Australian male), then convert to match
  the existing menu wavs (**22050 Hz, mono, 16-bit PCM**):
  ```bash
  edge-tts --voice en-AU-WilliamMultilingualNeural --text "Reboot." \
           --write-media /tmp/reboot.mp3
  ffmpeg -y -i /tmp/reboot.mp3 -ar 22050 -ac 1 -sample_fmt s16 \
         assets/sounds/effects/menu/reboot.wav
  ```
  Then `git add` the `.wav` (auto-LFS'd) and commit. Menu announcement effects
  live under `assets/sounds/effects/menu/`; 14-sound instrument "patches" under
  `assets/sounds/patches/<name>/`.
