import sys

class config:
	### top level config constants ###
	##								##

    PROJECT_ROOT = "../laserbox"
    DEBUG = True
    if sys.platform == 'linux':
    	FPS = 800
    else:
	    FPS = 60
    AUDIO_BUFFER = 2048         # samples
    REGISTER_DELAY = 0          # seconds
    SIM_SCREEN_WH = 600,480     # pixels
    ANTI_JITTER_DELAY = .05      # seconds
    CONGRATS_VOL = 0.75
    START_PROGRAM = "MusicMaker"
    PROGRAM_SEQUENCE = ['ClueFinder', 'TogglePattern', 'Flipper', 'TogglePattern', 'Golf' ]
    LASER_HOLD_PATTERN = [1,0,7,0,3,0,0,0] # post nathan-clue-one laser animation numberic code

    ### sub-config object for each Program subclass that needs one ###
    ##																##

    class Flipper:
    	START_BOARD = [1,0,1,0,1,0]
 
