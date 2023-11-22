import sys
import time
import pygame
from .. import config
from ..game_loop import Game
from ..audio_utils import Mixer

BLACK = (0,0,0)

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

class Simulator(Game):
    def __init__(self):
        super().__init__(PISOreg=DummyInputShiftRegister(),
                         SIPOreg=DummyOutputShiftRegister(),
                         mixer=Mixer())
        self.W = 600
        self.H = 480
        pygame.init()
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((self.W,self.H))
        self.frame = 0

    def render(self):
        self.screen.fill(BLACK)
        # -- #
        print('frame:',self.frame)
        pygame.display.flip()

    def update(self, dt):
        super().update(dt)
        self.frame += 1

    def run(self):
        self.dt = 1/self.FPS
        while True:
          self.update(self.dt)
          self.render()
          self.dt = self.clock.tick(self.FPS)


