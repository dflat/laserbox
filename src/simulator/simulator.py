"""Desktop simulator: dummy shift registers + a pygame view of the laser floor.

Run with ``python -m src -s``. :class:`Simulator` subclasses
:class:`~src.game_loop.Game`, swapping the real GPIO registers for keyboard- and
screen-backed dummies so the whole game can run without the physical box:

* :class:`DummyInputShiftRegister` maps keys ``0``-``9`` and ``a``-``f`` to the
  16 input bits (``e`` = toggle 0, ``f`` = toggle 1; toggles flip on keydown).
* :class:`DummyOutputShiftRegister` drives :class:`LaserPort` view objects.
* :class:`DummyLaserBay` lays the 14 ports out as the physical floor.
"""
import sys
import time
import pygame
from pygame import Surface
from pygame.locals import *
from .. import config
from ..game_loop import Game, LaserBay, GameClock
from ..audio_utils import Mixer
from ..event_loop import events
from ..config import config
import numpy as np
from math import sin, cos, pi

BLACK = (0,0,0)
WHITE = (255,255,255)
RED = (255,0,0)

def scale(verts, sx, sy):
    """Scale a set of 2D vertices by ``(sx, sy)``."""
    return (np.diag((sx,sy)) @ verts.T).T

def flip_y(verts):
    """Identity (a vertical-flip hook, currently disabled)."""
    return verts#(np.diag((1, -1)) @ verts.T).T

def rot_z(verts, phi):
    """Rotate a set of 2D vertices by angle ``phi`` (radians)."""
    return (np.array(((cos(phi), -sin(phi)),
                      (sin(phi), cos(phi)) )) @ verts.T).T

class GameObject:
    """Base for drawable simulator objects; ``group`` collects all instances."""
    group = []

class LaserPort(GameObject):
    """A drawn laser emitter: a triangle plus a beam line when on.

    Args:
        port_id: The laser index (0..13) this view represents.
        pos: ``(x, y)`` screen position of the emitter.
        laser_length: Beam length in pixels.
        direction: Unit ``(dx, dy)`` the beam points along.
    """
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
        self.direction = np.array(direction)
        self.on = False

    def get_image(self):
        surf = Surface()

    def update(self, dt):
        pass

    def _turn_on(self):
        self.on = True

    def _turn_off(self):
        self.on = False

    def render(self, surf):
        """Draw the emitter triangle and, if on, the red beam line."""
        pygame.draw.polygon(surf, WHITE, self.verts)
        if self.on:
            start = self.pos
            end = self.pos + self.direction*self.laser_length
            pygame.draw.line(surf, RED, start, end, width=3)


class DummyLaserBay(LaserBay):
    """A :class:`~src.game_loop.LaserBay` whose lasers are drawn :class:`LaserPort` views.

    Args:
        n: Number of lasers (default 14).
    """
    def __init__(self, n=14):
        self.n = n
        self.word = 0
        self.clean = True
        self.lasers = { }
        self._init_objects()

    def _init_objects(self):
        """Lay out the 14 ports as the physical floor (two rows + two sides)."""
        OFFSET = LaserPort.W/2 + LaserPort.PAD/2
        FLOOR_W = LaserPort.W*2 + LaserPort.PAD*3
        FLOOR_H = LaserPort.W*6 + LaserPort.PAD*7
        top, left = 100, (config.SIM_SCREEN_WH[0] - FLOOR_H) // 2
        PORT_IDS = [6,7,5,4,3,2,1,0,8,9,10,11,12,13]#[7,6,8,9,10,11,12,13,5,4,3,2,1,0]
        # numbering starts at 0 being bottom left, and wraps around counter-clockwise to 13
        for i in range(2):
            for j in range(6):
                x = left + (LaserPort.W + LaserPort.PAD)*j - i*OFFSET
                y = top + FLOOR_W*i
                direction = (0, (-1)**(i))
                port_id = PORT_IDS.pop()
                laser = LaserPort(pos=(x,y), direction=direction, laser_length=FLOOR_W, port_id=port_id)
                self.lasers[port_id] = laser
        for k in range(2):
            x1 = x + LaserPort.PAD*2
            y = top + (FLOOR_W - 2*LaserPort.H)/2*(k+1)
            direction = (-1, 0)
            port_id = PORT_IDS.pop()
            laser = LaserPort(pos=(x1,y), direction=direction, laser_length=FLOOR_H, port_id=port_id)
            self.lasers[port_id] = laser

class DummyOutputShiftRegister:
    """Stand-in output register: maps a pushed word onto the drawn lasers."""
    def __init__(self):
        print('init DummyOutputShiftRegister')
        pass

    def push_word(self, word):
        """Turn each :class:`LaserPort` on/off per the bit at its ``port_id``."""
        for laser in LaserPort.group:
            if word & (1 << laser.port_id):
                laser._turn_on()
            else:
                laser._turn_off()

class DummyInputShiftRegister():
    """Stand-in input register driven by the keyboard.

    Keys ``0``-``9`` and ``a``-``f`` map (hex) to the 16 input bits. ``e`` and
    ``f`` are the two toggles (they flip state on keydown); all other keys are
    momentary buttons (down while held).
    """
    def __init__(self):
        self.bitmap = {getattr(pygame,f'K_{c}'): i for i,c in enumerate('0123456789abcdef')}
        self.state = [0]*16

    def read_word(self):
        """Pump pygame events into ``self.state`` and return the 16-bit word."""
        word = 0x00
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                print(sum(dts)/len(dts))
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                bit = self.bitmap.get(event.key)
                if bit is not None:
                    if event.key in [pygame.K_e, pygame.K_f]: # toggles
                        if self.state[bit] == 1:
                            self.state[bit] = 0
                        else:
                            self.state[bit] = 1
                    else:
                        self.state[bit] = 1
            if event.type == pygame.KEYUP:
                bit = self.bitmap.get(event.key)
                if bit is not None:
                    if event.key in [pygame.K_e, pygame.K_f]: # toggles
                        continue
                    else:
                        self.state[bit] = 0

        for i in range(16):
            word |= (self.state[i] << i)
        return word
dts=[]
class Simulator(Game):
    """A :class:`~src.game_loop.Game` wired to the dummy registers + pygame view."""
    def __init__(self):
        super().__init__(PISOreg=DummyInputShiftRegister(),
                         SIPOreg=DummyOutputShiftRegister(),
                         mixer=Mixer(),
                         events=events)
        self.W, self.H = config.SIM_SCREEN_WH
        pygame.init()
        self.clock = GameClock(config.FPS) # pygame.time.Clock()
        self.screen = pygame.display.set_mode((self.W,self.H))
        self.frame = 0
        self.lasers = DummyLaserBay(14)

    def render(self):
        """Push the laser word, then redraw the floor."""
        super().render()
        self.screen.fill(BLACK)
        for laser in LaserPort.group:
            laser.render(self.screen)
        pygame.display.flip()

    def update(self, dt):
        """Run one game frame, then tick the view objects."""
        super().update(dt)
        self.frame += 1
        for laser in LaserPort.group:
            laser.update(dt)

    def run(self):
        """Run the simulator main loop."""
        self.dt = 1000/self.FPS  # ms, matching GameClock.tick()'s units
        print('hiell')
        while True:
          self.update(self.dt)
          self.render()
          self.dt = self.clock.tick()
          dts.append(self.dt)
