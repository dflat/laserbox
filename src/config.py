import sys

class config:
	### top level config constants ###
	##								##

    PROJECT_ROOT = "../laserbox"
    DEBUG = True
    if sys.platform == 'linux':
    	FPS = 100
    else:
	    FPS = 60
    AUDIO_BUFFER = int(2048/128)         # samples
    REGISTER_DELAY = 0          # seconds
    SIM_SCREEN_WH = 600,480     # pixels
    ANTI_JITTER_DELAY = .001      # seconds
    CONGRATS_VOL = 0.75
    START_PROGRAM = "MusicMaker"
    PROGRAM_SEQUENCE = ['ClueFinder', 'TogglePattern', 'Flipper', 'TogglePattern', 'Golf' ]
    LASER_HOLD_PATTERN = [7,0,1,0,3,0,0,0] # post nathan-clue-one laser animation numberic code

    ### sub-config object for each Program subclass that needs one ###
    ##																##

    class Flipper:
    	START_BOARD = [1,0,1,0,1,0]
 
    class Golf:
        GOALS_TO_COMPLETE = 3

    class GameSelect:
        # --- entry gesture ---
        # Hold all of TRIGGER_BUTTONS while toggle #TRIGGER_TOGGLE changes
        # state TRIGGER_TRANSITIONS times (e.g. on->off->on). All buttons must
        # stay held across every transition; releasing any one resets it.
        TRIGGER_BUTTONS = [0, 1]
        TRIGGER_TOGGLE = 0
        TRIGGER_TRANSITIONS = 2

        # ms an armed selection stays armed before clearing
        ARM_TIMEOUT_MS = 10000

        # button_id -> (launch_target, announcement_file)
        # launch_target resolves to a Program class name or a Composer class name.
        # announcement_file lives under assets/sounds/effects/menu/ .
        MENU = {
            0: ("Golf", "golf.wav"),
            1: ("Flipper", "flipper.wav"),
            2: ("ClueFinder", "clue_finder.wav"),
            3: ("MusicMaker", "music_maker.wav"),
            4: ("BirthdayComposer", "birthday.wav"),
        }
