"""Central configuration.

All tunables live as attributes on the :class:`config` class (referenced as
``config.NAME`` throughout the codebase). Per-program settings live in nested
classes (e.g. ``config.Flipper``, ``config.Golf``, ``config.GameSelect``).
"""

import sys


class config:
    """Top-level configuration constants and per-program sub-configs."""

    PROJECT_ROOT = "../laserbox"
    DEBUG = True
    # The Pi runs faster to keep input latency low; dev machines default to 60.
    if sys.platform == "linux":
        FPS = 100
    else:
        FPS = 60
    AUDIO_BUFFER = int(2048 / 128)  # samples
    REGISTER_DELAY = 0  # seconds (settle delay between GPIO edges)
    SIM_SCREEN_WH = 600, 480  # simulator window size, pixels
    ANTI_JITTER_DELAY = 0.001  # seconds (button-release debounce, e.g. Golf)
    CONGRATS_VOL = 0.75  # volume for the shared celebration sound
    START_PROGRAM = "MusicMaker"  # default for the ``-p`` CLI flag
    PROGRAM_SEQUENCE = [
        "ClueFinder",
        "TogglePattern",
        "Flipper",
        "TogglePattern",
        "Golf",
    ]
    LASER_HOLD_PATTERN = [
        7,
        0,
        1,
        0,
        3,
        0,
        0,
        0,
    ]  # post nathan-clue-one laser animation code

    ### sub-config object for each Program subclass that needs one ###
    ##                                                              ##

    class Flipper:
        """Settings for :class:`~src.programs.flipper.Flipper`."""

        # tuple (immutable) so it can't be mutated in place if ever aliased.
        START_BOARD = (1, 0, 1, 0, 1, 0)

    class Golf:
        """Settings for :class:`~src.programs.golf.Golf`."""

        GOALS_TO_COMPLETE = 3

    class SimonSays:
        """Settings for :class:`~src.programs.simon_says.SimonSays`."""

        PLAY_BUTTONS = (0, 1, 2, 3, 4, 5)  # front-row lasers/buttons in play
        WIN_LENGTH = 10  # pattern length that wins the game
        LIVES = 3  # mistakes allowed before a restart
        ON_MS = 450  # how long each demo step stays lit
        GAP_MS = 200  # dark gap between demo steps
        CHEER_MS = 1100  # pause after a cleared round (covers the affirmation)
        IDLE_MS = 15000  # re-show pattern after this idle time
        PATCH = "kicks_ascending_mono"  # one ascending tone per button

    class GameSelect:
        """Settings for :class:`~src.programs.game_select.GameSelect`."""

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
            5: ("SimonSays", "simon_says.wav"),
        }
