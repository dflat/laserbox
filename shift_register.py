import time
import RPi.GPIO as GPIO

class OutputShiftRegister:
    DELAY = 1e-4 # 100us 
	def __init__(self, RCLK=1, SRCLK=2, SER=3, n_outputs=16):
        self.RCLK = RCLK
        self.SRCLK = SRCLK
        self.SER = SER
        self.n_outputs = n_outputs
        self._init()

    def _init(self):
        GPIO.setmode(GPIO.BCM)
        chan_list = [self.RCLK, self.SRCLK, self.SER]
        GPIO.setup(chan_list, GPIO.OUT, initial=GPIO.LOW)
        self.clear()

    def push_bit(self, bit):
        GPIO.output(self.SER, bit)
        self.pulse(self.SRCLK) 

    def push_word(self, word):
        for i in reversed(range(self.n_outputs)):
            bit = word & (1 << i)
            self.push_bit(bit)
        self.pulse(self.RCLK)

    def clear(self):
        self.push_word(0)

    def pulse(self, pin):
        GPIO.output(pin, 1)
        time.sleep(self.DELAY)
        GPIO.output(pin, 0)



