import sys
import time
import pygame
from pygame import Surface
from pygame.locals import *
from .. import config
from ..game_loop import Game
from ..audio_utils import Mixer
import numpy as np
from math import sin, cos, pi

BLACK = (0,0,0)
RED = (255,0,0)

def scale(verts, sx, sy):
    return (np.diag((sx,sy)) @ verts.T).T

def flip_y(verts):
    return verts#(np.diag((1, -1)) @ verts.T).T

def rot_z(verts, phi):
    return (np.array(((cos(phi), -sin(phi)),
                      (sin(phi), cos(phi)) )) @ verts.T).T

class GameObject:
    group = []

class LaserPort(GameObject):
    W = 20
    H = 30
    PAD = 40
    UP = (0,1)
    BASE_VERTS = np.array([(-1,-1), (0,1), (1,-1)])
    VERTS = scale(BASE_VERTS, sx=W/2, sy=W/2)

    def __init__(self, port_id, pos, laser_length=40, direction=(1,0)):
        self.group.append(self)
        self.port_id = port_id
        self.pos = np.array(pos)
        self.verts = self.pos + rot_z(self.VERTS, np.arccos(np.dot(self.UP, direction)))
        self.laser_length = laser_length
        self.direction = direction
        self.on = True

    def get_image(self):
        surf = Surface()

    def update(self, dt):
        pass

    def turn_on(self):
        self.on = True

    def turn_off(self):
        self.on = False  

    def render(self, surf):
        pygame.draw.polygon(surf, RED, self.verts)
        if self.on:
            start = self.pos
            print('start', start)
            end = self.pos + self.direction*self.laser_length
            print('end', end)
            pygame.draw.line(surf, RED, start, end, width=3)



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
        self._init_objects()

    def _init_objects(self):
        top, left = 100, 100
        OFFSET = LaserPort.W/2 + LaserPort.PAD/2
        FLOOR_W = LaserPort.W*2 + LaserPort.PAD*3
        PORT_IDS = list(range(6)) + list(range(8,14)) + [6,7]
        # numbering starts at 0 being top left, and wraps around clockwise to 13
        for i in range(2):
            for j in range(6):
                x = left + (LaserPort.W + LaserPort.PAD)*j + i*OFFSET
                y = top + FLOOR_W*i
                direction = (0, (-1)**(i))
                LaserPort(pos=(x,y), direction=direction, port_id=PORT_IDS.pop())
        for k in range(2):
            x1 = x + LaserPort.PAD
            y = top + (FLOOR_W - 2*LaserPort.H)/2*(k+1)
            direction = (-1, 0)
            LaserPort(pos=(x1,y), direction=direction, port_id=PORT_IDS.pop())





    def render(self):
        self.screen.fill(BLACK)
        for laser in LaserPort.group:
            laser.render(self.screen)
        #print('frame:',self.frame)
        pygame.display.flip()

    def update(self, dt):
        super().update(dt)
        self.frame += 1
        for laser in LaserPort.group:
            laser.update(dt)

    def run(self):
        self.dt = 1/self.FPS
        while True:
          self.update(self.dt)
          self.render()
          self.dt = self.clock.tick(self.FPS)


