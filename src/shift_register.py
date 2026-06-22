"""Hardware drivers for the input/output shift registers.

laserbox reads 16 inputs (14 buttons + 2 toggles) through a 74HC165 PISO
register and drives 16 outputs (14 lasers + 2 spare) through a 74HC595 SIPO
register, both bit-banged over the Raspberry Pi's GPIO (BCM numbering).

``RPi.GPIO`` only exists on the Pi, so the import is guarded: it is skipped on
non-Linux platforms and when running the simulator (``-s``). The desktop
simulator substitutes dummy register classes (see
:mod:`src.simulator.simulator`) that satisfy the same ``read_word`` /
``push_word`` interface.
"""
import time
import sys
from .config import config
if sys.platform == 'linux' and '-s' not in sys.argv:
    import RPi.GPIO as GPIO


class OutputShiftRegister:
    """Driver for the 74HC595 SIPO (serial-in, parallel-out) shift register.

    Shifts a word out one bit at a time on ``SER`` (clocked by ``SRCLK``), then
    latches it to the parallel outputs with a pulse on ``RCLK``.

    Args:
        RCLK: BCM pin for the storage-register (latch) clock.
        SRCLK: BCM pin for the shift-register clock.
        SER: BCM pin for serial data in.
        n_outputs: Number of output bits (across cascaded chips).
    """
    DELAY = config.REGISTER_DELAY #1e-4 # 100us
    def __init__(self, RCLK=3, SRCLK=4, SER=2, n_outputs=16):
        self.RCLK = RCLK    # output
        self.SRCLK = SRCLK  # output
        self.SER = SER      # output
        self.n_outputs = n_outputs
        self._init()

    def _init(self):
        """Configure the GPIO pins as outputs and clear the register."""
        GPIO.setmode(GPIO.BCM)
        chan_list = [self.RCLK, self.SRCLK, self.SER]
        GPIO.setup(chan_list, GPIO.OUT, initial=GPIO.LOW)
        self.clear()

    def push_bit(self, bit):
        """Shift a single bit in on ``SER`` and pulse the shift clock."""
        GPIO.output(self.SER, bit)
        self.pulse(self.SRCLK)

    def push_word(self, word):
        """Shift ``word`` out MSB-first, then latch it to the outputs."""
        for i in reversed(range(self.n_outputs)):
            bit = word & (1 << i)
            self.push_bit(bit)
        self.pulse(self.RCLK)

    def clear(self):
        """Set all outputs low."""
        self.push_word(0)

    def pulse(self, pin):
        """Pulse ``pin`` high then low (a clock edge)."""
        GPIO.output(pin, 1)
        #time.sleep(self.DELAY)
        GPIO.output(pin, 0)



class InputShiftRegister:
    """Driver for the 74HC165 PISO (parallel-in, serial-out) shift register.

    Latches the parallel inputs by toggling ``SH_LD``, then clocks the bits out
    one at a time on ``QH`` (clocked by ``CLK``).

    Args:
        SH_LD: BCM pin for shift/load (IC pin 1).
        CLK: BCM pin for the clock (IC pin 2).
        QH: BCM pin reading serial data out of the cascaded IC (pin 10).
        n_outputs: Number of input bits (across cascaded chips).
    """
    DELAY = config.REGISTER_DELAY #1e-4 # 100us
    def __init__(self, SH_LD=21, # to IC pin # 1
                        CLK=20,  # to IC pin # 2
                        QH=16,  # from cascaded IC pin # 10
                        n_outputs=16):
        self.SH_LD = SH_LD  # output
        self.CLK = CLK      # output
        self.QH = QH      # input
        self.n_outputs = n_outputs
        self._init()

    def _init(self):
        """Configure SH_LD/CLK as outputs and QH as input."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.SH_LD, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.CLK, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.QH, GPIO.IN)

    def read_word(self):
        """Latch the inputs and clock them in, returning the 16-bit word."""
        GPIO.output(self.SH_LD, 0)
        #time.sleep(self.DELAY)    # Take snapshot of button state
        GPIO.output(self.SH_LD, 1)

        word = 0x00
        for i in reversed(range(self.n_outputs)):
            bit = GPIO.input(self.QH)
            word |= (bit << i)
            self.pulse(self.CLK)
            #time.sleep(self.DELAY)
        return word

    def pulse(self, pin):
        """Pulse ``pin`` high then low (a clock edge)."""
        GPIO.output(pin, 1)
        #time.sleep(self.DELAY)
        GPIO.output(pin, 0)
