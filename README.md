# Laserbox

Firmware for a physical, integrated **laser-arcade box/table**. The player stands
at a single unit with **14 buttons + 2 toggle switches** and **14 laser ports**,
driven by a Raspberry Pi through two shift registers (74HC165 input, 74HC595
output). It's a **reusable multi-game platform**: each experience is a set of
`Program` mini-games wired together by a `Composer`.

A pygame **simulator** lets you develop without any hardware.

---

## Quick start (development)

```bash
git clone git@github.com:dflat/laserbox.git
cd laserbox

# audio lives in Git LFS — see "Assets & Git LFS" below (one-time setup)
git lfs install
git lfs pull

# run against the on-screen simulator (no Pi/hardware needed)
python3 -m src -s
```

Run on the real hardware (on the Pi) with `python3 -m src`.

**Dependencies:** Python 3, `pygame`, `numpy` (plus `RPi.GPIO` on the Pi; the GPIO
import is skipped automatically off-Pi and in simulator mode).

---

## Repository layout

```
src/
  __main__.py        # entry point: python3 -m src [-s]
  game_loop.py       # fixed-timestep update→render loop (Game.run)
  event_loop.py      # event types + singleton event queue
  io_managers.py     # InputManager (button/toggle events) / OutputManager
  shift_register.py  # GPIO drivers (74HC165 in, 74HC595 out)
  animation.py       # laser animations (Frame/FrameSequence/Animation)
  audio_utils.py     # pygame Mixer: music, one-shot effects, 14-wav patches
  config.py          # constants + per-program config
  simulator/         # pygame keyboard simulator + dummy registers
  programs/          # mini-games (clue_finder, flipper, golf, simon_says,
                     #   music_maker, trivia, toggle_pattern, game_select, …)
assets/              # audio (WAV) — managed with Git LFS (see below)
docs/
  dev/               # architecture, audio, authoring-programs, hardware, …
  ops/system-setup.md# Raspberry Pi system/OS setup & deploy runbook
```

See `docs/dev/architecture.md` and `docs/dev/authoring-programs.md` to go deeper.

---

## Assets & Git LFS

All audio (`assets/**/*.wav`, ~170 MB) is tracked with **Git LFS**. If you've
never used LFS, read this section once — the workflow is simple but the *mental
model* is what trips people up.

### How it works (the mental model)

Git LFS keeps huge binaries out of normal git history. For every tracked file,
git stores only a tiny **pointer** (a ~130-byte text stub naming a content hash);
the real bytes — the **blob** — live in a separate LFS store. Smudge/clean
filters swap pointer↔blob transparently on checkout/commit, so in your working
tree a `.wav` looks completely normal.

What makes our setup specific: **code and blobs live in two different places.**

```
            ┌─────────────────────── git push / pull ───────────────────────┐
            │                                                                │
   ┌────────┴────────┐                                              ┌────────┴────────┐
   │     GitHub      │  code + tiny LFS *pointer* files             │  dev machine /  │
   │ dflat/laserbox  │ ───────────────────────────────────────────▶│   Pi (clients)  │
   └─────────────────┘                                              └────────┬────────┘
                                                                             │
                    git lfs push / pull  (the actual .wav bytes)            │
   ┌─────────────────────────────────────────┐                             │
   │   Forgejo on rjr's desktop (LFS store)   │◀────────────────────────────┘
   │   http://192.168.1.246:3000/rjr/laserbox │
   └─────────────────────────────────────────┘
```

- **Code + pointers → GitHub** (`origin`), as usual.
- **Audio blobs → a self-hosted Forgejo on rjr's desktop.** A committed
  `.lfsconfig` points every clone at it, so `git lfs` "just knows" where to go.
- **No GitHub LFS** is used (avoids its bandwidth quota); there's no per-byte cost.

> ⚠️ **The desktop must be powered on** for any `git lfs pull`/`push`. Plain
> `git pull`/`push` (code + pointers) works anytime via GitHub; only the audio
> bytes depend on the desktop being up.

### One-time setup on a new machine

```bash
git lfs install                      # install the smudge/clean filters (once per machine)
git config --global credential.helper store   # remember the LFS token (Linux/macOS)
git clone git@github.com:dflat/laserbox.git
cd laserbox
git lfs pull                         # first run prompts for credentials (see below)
```

**Credentials:** the Forgejo store authenticates over HTTP. At the first
`git lfs pull` you'll be prompted for the host `192.168.1.246:3000`:

- **Username:** `rjr`
- **Password:** the `laserbox-lfs` **access token** (ask rjr / grab it from
  Forgejo → *Settings → Applications*). It is **not** stored in this repo.

The credential helper saves it after the first time. On **Windows**, Git for
Windows ships **Git Credential Manager**, which pops a prompt once and remembers
it — no extra config needed.

### Daily workflow

**Get the latest audio** (after someone added/changed sounds):

```bash
git pull            # code + pointers from GitHub
git lfs pull        # download any new/changed audio blobs from Forgejo
```

**Add or change audio** on a dev machine, and propagate it everywhere:

```bash
# 1. drop/replace .wav files under assets/ (anything matching *.wav is auto-LFS'd)
cp ~/new_sound.wav assets/sounds/effects/new_sound.wav

# 2. commit — git stores a pointer; the blob is staged into LFS
git add assets/sounds/effects/new_sound.wav
git commit -m "audio: add new_sound effect"

# 3. push — pointers go to GitHub, the bytes go to the desktop's Forgejo
git push                       # (desktop must be ON; the pre-push uploads the blob)
```

Then on **the other dev machine and the Pi**, pull both halves:

```bash
git pull && git lfs pull
```

That's the whole sync story: **one `git push` from wherever you authored the
audio → `git pull && git lfs pull` on every other machine.** No rsync, no manual
copying, no drift.

### Where the blobs actually live (on the desktop)

The Forgejo service stores LFS objects on local disk, **content-addressed by
SHA-256**, under its data directory:

```
/var/lib/forgejo/data/lfs/<oid[0:2]>/<oid[2:4]>/<oid>
# e.g.  /var/lib/forgejo/data/lfs/70/d3/70d37a5c78839ffa…
```

Metadata (which repo owns which object) is in the SQLite DB at
`/var/lib/forgejo/data/forgejo.db` (`lfs_meta_object` table). The directory is
owned by the `forgejo` system user (mode 0750), so inspect it with sudo:

```bash
sudo du -sh /var/lib/forgejo/data/lfs     # ~179 MB of audio objects
```

Config: `/etc/forgejo/app.ini` (`[lfs] PATH`, `[server] LFS_START_SERVER`).
Manage the service with `systemctl {status,restart} forgejo`.

---

## Deploying to the Pi

The Pi is a plain LFS client. To ship new code and/or audio:

```bash
git -C /home/pi/electronics/laserbox pull --ff-only
git -C /home/pi/electronics/laserbox lfs pull      # if audio changed (desktop must be on)
systemctl --user restart laserbox
```

Full Pi/OS provisioning (audio routing, the systemd user service, boot tuning,
LFS install) is documented in **`docs/ops/system-setup.md`**.
