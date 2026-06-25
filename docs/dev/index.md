# laserbox developer docs

**laserbox** is the firmware for a physical, arcade-style interactive box. A
player stands at an integrated unit with **14 buttons + 2 toggle switches** and a
field of **14 lasers**, and plays a series of mini-games. It runs on a Raspberry
Pi, talking to the hardware through two shift registers, and ships with a desktop
**simulator** so you can develop without the box.

It is built as a **reusable multi-game platform**: the engine (clock, I/O, event
loop, audio, animations, state machine) is generic, and each game is a small
`Program` subclass. A `Composer` strings programs together into a show, and the
`GameSelect` menu lets an operator launch any game or composition on demand.

## Hardware at a glance

| Direction | Chip | Carries |
|-----------|------|---------|
| Input  | 74HC165 (PISO) | 14 buttons + 2 toggles (16-bit word) |
| Output | 74HC595 (SIPO) | 14 lasers + 2 spare (16-bit word) |

The Pi bit-bangs both registers over GPIO (BCM numbering). See {doc}`hardware`.

## Running it

From the repository root:

```bash
# Desktop simulator (no hardware needed) -- opens a pygame window.
python -m src -s

# Simulator, but boot straight into one program (skips the menu).
python -m src -s -p Golf

# On the Raspberry Pi, with real hardware:
python -m src
```

In the simulator, keys `0`-`9` and `a`-`f` map to the 16 input bits; `e` and `f`
are the two toggles. So to reach the menu from inside a game, hold `0` and `1`
and tap `e` twice. See {doc}`simulator`.

## Where to start

- {doc}`architecture` — the big picture: the frame loop and the
  input → event → program → output pipeline.
- {doc}`state-machine` — states, the state machine, contexts/composers, and the
  `Program` lifecycle.
- {doc}`authoring-programs` — **the guide to writing your own game.**
- {doc}`animation` and {doc}`audio` — the laser-animation and sound subsystems.
- {doc}`time` — the monotonic timing model: how to measure durations safely.
- {doc}`simulator` and {doc}`hardware` — dev workflow and wiring.
- {doc}`api/index` — the auto-generated API reference.

```{toctree}
:maxdepth: 2
:hidden:
:caption: Guides

architecture
state-machine
authoring-programs
animation
audio
time
simulator
hardware
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: Reference

api/index
```
