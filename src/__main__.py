import sys
print('importing Game')
from .game_loop import Game
print('importing ShiftRegister')
from .shift_register import *
print('importing Mixer')
from .audio_utils import Mixer
print('importing Simulator')
from .simulator.simulator import Simulator
print('importing Event Loop')
from .event_loop import events

print('loading src/__main__.py ...')
mixer = Mixer()

if '-s' in sys.argv:
    #PISOreg = DummyInputShiftRegister() 
    #SIPOreg = DummyOutputShiftRegister() 
    game = Simulator()
    game.run()
else:
    PISOreg = InputShiftRegister() 
    SIPOreg = OutputShiftRegister() 
    game = Game(PISOreg=PISOreg, SIPOreg=SIPOreg, mixer=mixer, events=events)
    game.run()


