import sys

class config:
    PROJECT_ROOT = "../laserbox"
    DEBUG = True
    if sys.platform == 'linux':
    	FPS = 800
    else:
	    FPS = 60
    AUDIO_BUFFER = 2048
    START_PROGRAM = "MusicMaker"
    REGISTER_DELAY = 0
    SIM_SCREEN_WH = 600,480
