import time
import sys
if sys.platform == 'linux':
    import RPi.GPIO as GPIO
else:
    import pygame

class OutputShiftRegister:
    """
    Driver for 74HC595 SIPO Shift Register
    """
    DELAY = 1e-4 # 100us 
    def __init__(self, RCLK=3, SRCLK=4, SER=2, n_outputs=16):
        self.RCLK = RCLK    # output
        self.SRCLK = SRCLK  # output
        self.SER = SER      # output
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



class InputShiftRegister:
    """
    Driver for 74HC165 PISO Shift Register
    """
    DELAY = 1e-4 # 100us 
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
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.SH_LD, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.CLK, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.QH, GPIO.IN)
        
    def read_word(self):
        GPIO.output(self.SH_LD, 0)
        time.sleep(self.DELAY)    # Take snapshot of button state
        GPIO.output(self.SH_LD, 1) 

        word = 0x00
        for i in reversed(range(self.n_outputs)):
            bit = GPIO.input(self.QH) 
            word |= (bit << i) 
            self.pulse(self.CLK)
            time.sleep(self.DELAY)
        return word

    def pulse(self, pin):
        GPIO.output(pin, 1)
        time.sleep(self.DELAY)
        GPIO.output(pin, 0)

class DummyOutputShiftRegister:
    def __init__(self):
        pass

class DummyInputShiftRegister():
    """
    Used for testing, standard keyboard numpad
    triggers inputs (0-9a-f, hex coded)
    """
    def __init__(self):
        self.bitmap = {getattr(pygame,f'K_{c}'): i for i,c in enumerate('0123456789abcdef')}
        self.state = [0]*16

    def read_word(self):
        word = 0x00
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                bit = self.bitmap.get(event.key)
                if bit is not None:
                    self.state[bit] = 1
            if event.type == pygame.KEYUP:
                bit = self.bitmap.get(event.key)
                if bit is not None:
                    self.state[bit] = 0
        for i in range(16):
            word |= (self.state[i] << i)
        return word
