import sys
from .game_loop import Game
from .shift_register import *
from .audio_utils import Mixer
from .simulator.simulator import Simulator

mixer = Mixer()

if '-s' in sys.argv:
    #PISOreg = DummyInputShiftRegister() 
    #SIPOreg = DummyOutputShiftRegister() 
    game = Simulator()
    game.run()
else:
    PISOreg = InputShiftRegister() 
    SIPOreg = OutputShiftRegister() 
    game = Game(PISOreg=PISOreg, SIPOreg=SIPOreg, mixer=mixer)
    game.run()


