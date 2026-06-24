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
            6: ("Trivia", "trivia.wav"),
        }

        # --- system power actions (last two physical buttons) ---
        # These do NOT launch a program; they reboot/shut down the box. To guard
        # against accidental triggering they use a three-press confirm flow (see
        # GameSelect): 1st press announces, 2nd press arms (plays ``confirm``),
        # 3rd press executes. Pressing any other button while armed cancels and
        # returns to the menu. ``announce``/``confirm`` are wavs under
        # assets/sounds/effects/menu/ ; ``action`` keys into SYSTEM_ACTIONS.
        SYSTEM_MENU = {
            12: dict(action="reboot",
                     announce="reboot.wav", confirm="reboot_confirm.wav"),
            13: dict(action="poweroff",
                     announce="shutdown.wav", confirm="shutdown_confirm.wav"),
        }

        # action -> argv run (fire-and-forget) when a SYSTEM_MENU slot is
        # confirmed. Verified on the box: the ``pi`` user has passwordless sudo
        # and ``systemctl`` is on PATH (the /sbin/reboot|poweroff shims are not),
        # so ``sudo systemctl <verb>`` is the robust invocation. systemd then
        # SIGTERMs the service and game_loop's handler clears lasers/audio/GPIO.
        SYSTEM_ACTIONS = {
            "reboot": ["sudo", "systemctl", "reboot"],
            "poweroff": ["sudo", "systemctl", "poweroff"],
        }

    class Trivia:
        """Settings for :class:`~src.programs.trivia.Trivia`.

        Two-player face-off: **Black team** (left half, keys 0-6) versus **White
        team** (right half, keys 7-13). Each team buzzes with its endcap button
        and answers on its four choice buttons. Choice *slot* ``i`` (0..3) maps to
        ``BLACK_CHOICES[i]`` / ``WHITE_CHOICES[i]`` so the two halves are mirror
        images (black button 0 == white button 13, etc.).
        """

        # --- match shape ---
        QUESTIONS_PER_MATCH = 7       # questions per match; highest score wins
        DIFFICULTY = "any"            # any | easy | medium | hard (OpenTDB filter)
        CATEGORY = None               # None = any; else an OpenTDB category id (int)

        # --- timing (milliseconds) ---
        ANSWER_TIMEOUT_MS = 30000     # lock-in deadline after a buzz (auto-picks an armed choice)
        POST_QUESTION_BUZZ_MS = 30000  # buzz window after a question reads out untouched
        WARNING_MS = 5000             # "five seconds remaining" warning before either deadline
        VO_GAP_MS = 120               # gap inserted between chained voice-over clips
        READY_REPROMPT_MS = 12000     # re-announce "buzz to begin" if a team stalls

        # --- teams (named for the keycap colours on each half of the box) ---
        BLACK_BUZZ = 6                # left endcap
        WHITE_BUZZ = 7                # right endcap
        BLACK_CHOICES = (0, 1, 2, 3)        # choice slot i -> this button id
        WHITE_CHOICES = (13, 12, 11, 10)    # mirror of the black side

        # --- scoring (a team may legitimately sit negative) ---
        SCORE_FIRST_RIGHT = 2         # buzz first and answer correctly
        SCORE_FIRST_WRONG = -1        # buzz first and miss (discourages blind buzzing)
        SCORE_STEAL_RIGHT = 1         # take the steal correctly (you had more info)
        SCORE_STEAL_WRONG = 0         # whiff the steal (no extra penalty)

        # --- source / voice selection ---
        # FORCE_MODE: None auto-detects at start(); otherwise pin a (source, voice)
        # pair, e.g. ("bank", "prebaked") or ("live", "piper"). The impossible
        # combo ("live", "prebaked") is auto-corrected (you can't pre-bake an
        # unknown live question).
        FORCE_MODE = None
        # CURATED_PLAYLIST: None = random-distinct sample of QUESTIONS_PER_MATCH.
        # Otherwise an ordered list of bank question ids (str) or positional indices
        # (int) -> a fixed "determined" match whose length becomes len(the list).
        CURATED_PLAYLIST = None
        FETCH_TIMEOUT_S = 3           # OpenTDB request timeout, seconds (live mode)
        # Only relevant if/when a runtime TTS path exists; piper cannot run on the
        # box's ARMv6 Pi Zero W, so PiperVoice is currently a stub.
        PIPER_MODEL = "en_GB-alan-medium"

        # --- asset paths ---
        BANK_PATH = "assets/trivia/bank.json"  # question bank (JSON), repo-relative
        EFFECT_DIR = "trivia"          # voice-over root under assets/sounds/effects
