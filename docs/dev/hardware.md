# Hardware

laserbox runs on a Raspberry Pi that bit-bangs two shift registers over GPIO
(BCM numbering). Drivers are in {mod}`src.shift_register`.

```{note}
The pin assignments below are the **defaults declared in code**
({class}`~src.shift_register.InputShiftRegister` /
{class}`~src.shift_register.OutputShiftRegister`). They are the source of truth
for the firmware; physical wiring must match them (or pass different pins when
constructing the registers).
```

## Input — 74HC165 (PISO)

Reads 16 inputs (14 buttons + 2 toggles) into one word.

| Signal | BCM pin | IC pin | Direction |
|--------|---------|--------|-----------|
| `SH_LD` | 21 | 1 | out (latch inputs) |
| `CLK`   | 20 | 2 | out (shift clock) |
| `QH`    | 16 | 10 (cascaded) | in (serial data) |

{meth}`~src.shift_register.InputShiftRegister.read_word` pulses `SH_LD` to snapshot
the parallel inputs, then clocks 16 bits in on `QH`.

## Output — 74HC595 (SIPO)

Drives 16 outputs (14 lasers + 2 spare) from one word.

| Signal | BCM pin | Direction |
|--------|---------|-----------|
| `SER`   | 2 | out (serial data) |
| `SRCLK` | 4 | out (shift clock) |
| `RCLK`  | 3 | out (latch/storage clock) |

{meth}`~src.shift_register.OutputShiftRegister.push_word` shifts the word out
MSB-first on `SER` (clocked by `SRCLK`), then pulses `RCLK` to latch it to the
parallel outputs.

## The 16-bit word layout

Both directions use the same bit layout:

```
 bit:  15   14   13 12 11 10  9  8  7  6  5  4  3  2  1  0
      ┌────┬────┬───────────────────────────────────────┐
 in:  │ t1 │ t0 │            buttons 13 .. 0             │
      └────┴────┴───────────────────────────────────────┘
      ┌────┬────┬───────────────────────────────────────┐
 out: │ sp │ sp │            lasers  13 .. 0             │
      └────┴────┴───────────────────────────────────────┘
```

- Input: bits 0–13 are buttons, bits 14–15 are toggles 0 and 1. This is exactly
  what {class}`src.programs.base.State` decodes (`buttons` / `toggles`).
- Output: bits 0–13 are lasers; bits 14–15 are spare
  ({class}`src.io_managers.OutputManager` defines `laser_mask` / `extra_mask`).

## The GPIO import guard

`RPi.GPIO` only exists on the Pi, so the import is guarded:

```python
if sys.platform == 'linux' and '-s' not in sys.argv:
    import RPi.GPIO as GPIO
```

It is skipped on non-Linux and whenever the simulator (`-s`) runs, so the same
codebase imports cleanly on a dev machine. The desktop {doc}`simulator`
substitutes dummy registers that satisfy the same `read_word()` / `push_word()`
interface.

## Laser layout

The physical floor is two rows of six laser ports plus two longer side lasers.
The simulator reproduces this layout in
{meth}`DummyLaserBay._init_objects <src.simulator.simulator.DummyLaserBay>`,
which also documents the port-id ordering (0 at bottom-left, wrapping
counter-clockwise to 13).
