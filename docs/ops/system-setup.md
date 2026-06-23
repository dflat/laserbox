# Laserbox Pi — System Setup & Change Log

> Authoritative record of every OS/system-level change required to run the
> laserbox firmware on this Raspberry Pi, **so the whole box can be rebuilt from
> a fresh SD card**. Covers (1) changes made during the 2026-06-22 setup
> session, (2) pre-existing modifications found on the box, and (3) a
> step-by-step rebuild runbook.
>
> Application *code* lives in git (`github.com:dflat/laserbox`, branch `main`)
> and is **not** duplicated here — this document is only the system/OS layer.

| | |
|---|---|
| **Host** | `rzero` — Raspberry Pi **Zero W Rev 1.1** (single-core ARMv6) |
| **OS** | Raspbian GNU/Linux 12 (bookworm), kernel `6.1.0-rpi6-rpi-v6`, 32-bit `armv6l` |
| **Ethernet IP** | `192.168.1.244` (hard-wired; reachable as `box-ether` from rjr's laptop) |
| **App user** | `pi` (uid 1000) |
| **Repo path** | `/home/pi/electronics/laserbox` |
| **Audio** | PipeWire (PulseAudio shim) → onboard `bcm2835` PWM analog out on GPIO 12/13 |
| **Doc created** | 2026-06-22 |

---

## 0. TL;DR — rebuild order

1. Flash **Raspberry Pi OS (bookworm, 32-bit)** for the Pi Zero W.
2. Base config (raspi-config / imager): hostname `rzero`, timezone
   `America/New_York`, **console autologin for `pi`**, enable SSH.
3. Edit `/boot/firmware/config.txt` → audio routing + disable BT (§Rebuild 3).
4. `sudo apt install -y python3-pygame python3-rpi.gpio git`.
5. Authorize SSH keys (§Rebuild 5); set up the Pi's GitHub key or clone via HTTPS.
6. `git clone` the repo to `/home/pi/electronics/laserbox` **and rsync the
   `assets/` audio** (assets are gitignored — clone alone is not enough).
7. Install the systemd **user** service (§2.2), `enable-linger`, enable it.
8. Disable the non-essential services (§2.4).
9. Reboot and run the verification checklist (§4).

---

## 1. Why a systemd *user* service (the central design decision)

The app must auto-start at boot, drive GPIO, and play audio. We run it as a
**systemd user service for `pi`** (not a system service) because:

- **Audio** is PipeWire living in the `pi` user session. A *system* service
  (even `User=pi`) can't reach the user's PipeWire socket without fragile
  `XDG_RUNTIME_DIR`/PulseAudio plumbing. A user service inherits it for free.
- **GPIO** needs no root: `pi` is in the `gpio` group and RPi.GPIO uses
  `/dev/gpiomem` (group-accessible), so root is unnecessary.
- **Boot without login**: `loginctl enable-linger pi` starts the user manager
  (and its enabled services, incl. PipeWire and laserbox) at boot regardless of
  whether anyone logs in.

Trade-off accepted: time-to-game is gated by how fast udev gives `/dev/gpiomem`
its `gpio` group (~tens of seconds on this slow Pi Zero); a root system service
could start sooner but would reintroduce the audio problem. Not worth it.

---

## 2. Changes made on 2026-06-22 (this is what to re-apply)

### 2.1 SSH key access
- Appended rjr's laptop public key (`~/.ssh/id_ed25519.pub`) to
  `/home/pi/.ssh/authorized_keys` (done via `ssh-copy-id`). Enables passwordless
  login as `pi@192.168.1.244`.
- **Client side** (rjr's laptop, *not* the Pi): added a `~/.ssh/config` alias:
  ```
  Host box-ether
      HostName 192.168.1.244
      User pi
      IdentityFile ~/.ssh/id_ed25519
      IdentitiesOnly yes
  ```

### 2.2 systemd user service `laserbox.service`
File: **`/home/pi/.config/systemd/user/laserbox.service`** (created by us).

```ini
[Unit]
Description=Laserbox arcade firmware (python3 -m src)
After=pipewire.service wireplumber.service
# Kiosk: never give up restarting (a slow boot must not leave it dead).
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=/home/pi/electronics/laserbox
Environment=PYTHONUNBUFFERED=1
Environment=SDL_VIDEODRIVER=dummy
# Don't let SDL install a SIGTERM/SIGINT handler (it just posts an unhandled
# pygame "quit" event, so the process ignores SIGTERM and systemd has to wait
# the full stop timeout, stalling shutdown ~90s). With this, SIGTERM exits at once.
Environment=SDL_NO_SIGNAL_HANDLERS=1
# Hard cap on shutdown regardless: SIGKILL 8s after SIGTERM if it hasn't exited.
TimeoutStopSec=8
# Wait (up to 60s) until udev has given /dev/gpiomem its `gpio` group so the
# pi user can use it. Without this, an early-boot start races udev, RPi.GPIO
# falls back to /dev/mem, and dies with "No access to /dev/mem. Try as root!".
ExecStartPre=/bin/bash -c 'for i in $(seq 1 120); do [ -r /dev/gpiomem ] && [ -w /dev/gpiomem ] && exit 0; sleep 0.5; done; echo "gpiomem still inaccessible after 60s" >&2; exit 1'
ExecStart=/usr/bin/python3 -m src
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

**Why each non-obvious line exists:**
- `ExecStartPre` gpiomem-wait — on a cold boot the service starts before udev
  has chgrp'd `/dev/gpiomem` to group `gpio`; RPi.GPIO then falls back to
  root-only `/dev/mem` and crashes (`No access to /dev/mem`). Originally this
  crash-looped ~5× over ~90s before luck. The wait makes startup deterministic.
- `SDL_NO_SIGNAL_HANDLERS` + `TimeoutStopSec=8` — backstops for clean shutdown
  (the real fix is the in-app SIGTERM handler, see §2.5). Without a fast stop,
  the user service stalled system shutdown ~90s, making reboots take ~2.5 min.
- `StartLimitIntervalSec=0` — never give up restarting.
- `SDL_VIDEODRIVER=dummy` — the real game opens no window; prevents any stray
  pygame display init from failing headless.
- `After=pipewire…` — order audio first.

### 2.3 Enable linger + the service
```bash
sudo loginctl enable-linger pi
systemctl --user daemon-reload
systemctl --user enable --now laserbox.service
```

### 2.4 Disabled non-essential services (faster boot)
An arcade box needs none of these; disabling cut ~35s off boot. **Reversible**
with `systemctl enable …`.
```bash
sudo systemctl disable --now cups.service cups.socket cups.path cups-browsed.service
sudo systemctl disable --now ModemManager.service
sudo systemctl disable NetworkManager-wait-online.service
```
- `cups*` — printing (was ~22.6s on the boot critical path). No printer.
- `ModemManager` — cellular/USB-modem manager. None attached.
- `NetworkManager-wait-online` — only *blocks boot* until NM reports
  connectivity (~16s). Nothing on the box needs network-at-boot; `sshd` binds
  wildcard. Networking/SSH still come up normally, just not gated.

### 2.5 Application code (in git — reference only)
These are *code* fixes, deployed by `git pull` on the Pi, not system config:
- `feat(game_loop): clean SIGTERM/SIGINT shutdown; lasers off on start & exit`
  (`6746f9e`) — installs a real signal handler so `systemctl stop` exits in
  <1s (was ~90s) and clears lasers + audio + GPIO on exit.
- `fix(Flipper): stop leaking board state across re-entries` (`5609d37`).

To redeploy code: `git -C /home/pi/electronics/laserbox pull --ff-only` then
`systemctl --user restart laserbox`.

---

## 3. Pre-existing system modifications (NOT made by us, but required)

Found on the box; presumably set up previously to make laserbox/audio/GPIO work.
**Must be reproduced on a fresh SD** (except where noted cosmetic/unrelated).

### 3.1 `/boot/firmware/config.txt` — audio + Bluetooth  ⚠️ critical
Non-stock lines under `[all]`:
```ini
dtoverlay=audremap,pins_12_13   # route PWM analog audio to GPIO 12 & 13
dtoverlay=disable-bt            # disable onboard Bluetooth
```
- **`audremap,pins_12_13` is essential for sound.** The Pi Zero W has no 3.5mm
  jack; this maps the onboard PWM audio to GPIO 12/13 (wired to the box's amp/
  speaker). Without it there is effectively no analog audio out. This is why the
  default sink is `alsa_output.platform-bcm2835_audio…`.
- `disable-bt` — frees the PL011 hardware UART / drops unused Bluetooth.
- Note: `dtparam=audio=on` is present (stock). SPI/I2C params remain **commented
  out** (`#dtparam=spi=on`, `#dtparam=i2c_arm=on`) — laserbox bit-bangs the
  74HC165/74HC595 over plain GPIO, so no hardware SPI/I2C is needed.

### 3.2 Console autologin for `pi` on tty1
`/etc/systemd/system/getty@tty1.service.d/autologin.conf` (raspi-config "console
autologin"):
```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
```
Boots to console (default target `multi-user.target`) and auto-logs-in `pi`,
keeping a user session (and PipeWire) alive. With linger enabled this is not
strictly required for the service to start, but it matches the working setup.

### 3.3 Pre-existing SSH access
- `authorized_keys` already contained a key commented **`rsync-laserbox`** — the
  deploy/asset-sync key from the dev machine (see §3.6). Keep it.
- The Pi has its **own** `~/.ssh/id_ed25519[.pub]` used as the **outbound**
  credential for the git SSH remote `git@github.com:dflat/laserbox.git`
  (a GitHub deploy key or added to the account). Needed for `git pull/clone`.

### 3.4 Host identity / locale
- Hostname set to **`rzero`** (default would be `raspberrypi`).
- Timezone **`America/New_York`** (default UTC).

### 3.5 Audio level
- ALSA `bcm2835` `PCM` playback volume set to **~97% (+1.25 dB)**. Adjust with
  `amixer -c <card> sset PCM <pct>%` or via PipeWire/`wpctl`.

### 3.6 Repo + assets layout  ⚠️ assets are NOT in git
- Repo cloned to `/home/pi/electronics/laserbox`, remote
  `git@github.com:dflat/laserbox.git`, branch `main`.
- **`assets/` (audio) is `.gitignore`d** and managed outside git — a fresh
  `git clone` will be missing all sound files and the app's audio will fail to
  load. The `assets/sounds/**` tree must be **rsync'd/copied** onto the box
  (this is what the `rsync-laserbox` key is for).

### 3.7 Other (pre-existing, not laserbox-related)
- Extra `sudoers.d` drop-ins exist: `010_pi-nopasswd` (stock RPi: `pi` =
  passwordless sudo, relied upon by §2.3/§2.4), plus `010_at-export`,
  `010_global-tty`, `010_proxy`, `010_wiz-nopasswd` — pre-existing, unrelated to
  laserbox; review/port only if you actually use them.
- `~/.bashrc`: convenience alias `laser='cd ~/electronics/laserbox'`.

### 3.8 Stock behavior we rely on (do NOT need to recreate — RPi OS default)
- `pi` is in groups `gpio,spi,i2c,audio,input,video,dialout,netdev,…` by default
  — we did **not** add the `gpio` group; the boot issue was udev *timing*, not
  membership.
- `/etc/udev/rules.d/99-com.rules` ships the rule
  `SUBSYSTEM=="*gpiomem*", GROUP="gpio", MODE="0660"` (stock). Our service waits
  for *this* rule to take effect; the rule itself needs no editing.

---

## 4. Rebuild runbook (fresh SD → working box)

Run as `pi` on the freshly imaged Pi (over SSH or console).

**1. Base config** (raspi-config or Imager advanced options):
```bash
sudo raspi-config nonint do_hostname rzero
sudo timedatectl set-timezone America/New_York
sudo raspi-config nonint do_boot_behaviour B2   # console autologin
# enable SSH if not already: sudo raspi-config nonint do_ssh 0
```

**2. config.txt — audio + BT** (append under the `[all]` section):
```bash
sudo tee -a /boot/firmware/config.txt >/dev/null <<'CFG'

[all]
dtoverlay=audremap,pins_12_13
dtoverlay=disable-bt
CFG
# ensure `dtparam=audio=on` is present (it is by default)
```

**3. Packages:**
```bash
sudo apt update
sudo apt install -y python3-pygame python3-rpi.gpio git rsync
```

**4. SSH keys:**
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
# inbound: add rjr's laptop key + the rsync-laserbox key
cat >> ~/.ssh/authorized_keys <<'KEYS'
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEqBTfXzkX7yOAevz3ciTs0HQwB64VMRSzZyVG1rm+TT rsync-laserbox
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBb+dgV5ADTblZtph7UhjSrIwumFGQg+w9WtP1jVXxxO
KEYS
chmod 600 ~/.ssh/authorized_keys
# outbound (for git SSH): reuse the old key or generate + add to GitHub as a deploy key
#   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''
#   (then add ~/.ssh/id_ed25519.pub to the dflat/laserbox GitHub deploy keys)
```

**5. Code + assets:**
```bash
mkdir -p /home/pi/electronics
git clone git@github.com:dflat/laserbox.git /home/pi/electronics/laserbox
# OR https: git clone https://github.com/dflat/laserbox.git /home/pi/electronics/laserbox
# >>> copy the audio assets (NOT in git) <<<
#   from the dev machine:  rsync -av assets/ box-ether:/home/pi/electronics/laserbox/assets/
```

**6. systemd user service** — create
`~/.config/systemd/user/laserbox.service` with the contents from §2.2, then:
```bash
sudo loginctl enable-linger pi
systemctl --user daemon-reload
systemctl --user enable --now laserbox.service
```

**7. Disable non-essential services** — commands from §2.4.

**8. Reboot:** `sudo reboot`, then run §5.

---

## 5. Verification checklist (after reboot)
```bash
ssh box-ether
export XDG_RUNTIME_DIR=/run/user/1000
systemctl --user is-active laserbox.service                 # -> active
systemctl --user show laserbox.service -p NRestarts --value # -> 0
journalctl --user -u laserbox.service -b | grep -c 'No access to /dev/mem'   # -> 0
journalctl --user -u laserbox.service -b | grep 'loaded program: GameSelect' # -> present
loginctl show-user pi | grep Linger                         # -> Linger=yes
aplay -l                                                    # bcm2835 Headphones present
# clean shutdown is fast:
time systemctl --user stop laserbox.service                 # -> < 1s
systemctl --user start laserbox.service
```
Expected: boots straight into GameSelect, audio plays the menu prompt, buttons/
lasers respond, `systemctl stop` returns in well under a second.

---

## 6. Day-to-day management
```bash
ssh box-ether
export XDG_RUNTIME_DIR=/run/user/1000            # needed for --user over SSH
systemctl --user status   laserbox               # state
systemctl --user restart  laserbox               # after a git pull
systemctl --user stop     laserbox               # take it down
journalctl  --user -u laserbox -f                # live logs
git -C /home/pi/electronics/laserbox pull --ff-only && systemctl --user restart laserbox
```

---

## 7. Appendix — key facts
- Python `3.11.2`; `python3-pygame 2.1.2+dfsg-5`, `python3-rpi.gpio 0.7.1~a4-1+b2` (apt).
- App entrypoint: `python3 -m src` from the repo root (no `-s` = real GPIO; `-s`
  = pygame simulator, dev machines only).
- Shift registers: 74HC165 (PISO, inputs) + 74HC595 (SIPO, lasers), bit-banged
  over GPIO — no hardware SPI/I2C overlay required.
- `dphys-swapfile` swap = 100 MB (stock).
- Boot target: `multi-user.target` (console, no desktop, though `lightdm` is
  installed).
