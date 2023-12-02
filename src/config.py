import sys

class config:
    PROJECT_ROOT = "../laserbox"
    DEBUG = True
    if sys.platform == 'linux':
    	FPS = 800
    else:
	    FPS = 60
    AUDIO_BUFFER = 2048         # samples
    START_PROGRAM = "MusicMaker"# class name
    REGISTER_DELAY = 0          # seconds
    SIM_SCREEN_WH = 600,480     # pixels
    ANTI_JITTER_DELAY = .05      # seconds
    CONGRATS_VOL = 0.75

    class Flipper:
    	START_BOARD = [1,0,0,1,0,0]
