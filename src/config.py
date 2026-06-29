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
    # Mixer buffer, in samples (must be a power of two). At 22050 Hz this is the
    # amount of audio SDL pre-mixes per callback: too small and the callback
    # can't be serviced in time (the OS scheduler / GIL / the 100 FPS loop steal
    # it), starving the device -> underruns heard as crackle/pops/dropped frames.
    # 1024 samples ~= 46 ms, the floor that stays glitch-free on the Pi Zero W's
    # single ARMv6 core while keeping press->sound latency low. (Was briefly 16
    # samples ~= 0.7 ms chasing latency, which is far below any audio device's
    # period and crackled everywhere -- on the Pi and on dev machines alike.)
    AUDIO_BUFFER = 1024  # samples
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

        # A fresh board is dealt at random on entry; the lit-laser count is
        # bounded so the deal is never empty and never an instant win (all six).
        MIN_START_ON = 1
        MAX_START_ON = 5

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
        PATCH = "kicks_ascending_mono"  # one ascending tone per button

    class Catch:
        """Settings for :class:`~src.programs.catch.Catch`."""

        # The blip ping-pongs across lasers 0..N_PORTS-1 (the left/black side).
        N_PORTS = 6  # lasers the blip travels across (0..5)
        # Candidate target ports, re-rolled each round. The interior of the row is
        # used -- not the 0/5 turnaround ends, which the blip visits half as often
        # (and port 0 is also the spawn) -- so every round's target gets equal
        # catch windows regardless of where it lands.
        TARGET_PORTS = (1, 2, 3, 4)
        BLINK_HZ = 2  # target blink rate while waiting/chasing (twice a sec)

        # ms per blip move at each progression level; each level is faster than
        # the last. The player climbs one level per successful catch (the blip
        # bounces forever until they press); a miss restarts from level 1. The
        # first is the spec's 120 ms (~8.3 moves/sec); the fourth is a slight step
        # up in speed over the third. Length sets the level count and must match
        # ``LEVEL_SOUNDS``.
        LEVEL_STEP_MS = (120, 90, 65, 50)

        LEVEL_ADVANCE_MS = 1500  # pause (under the announcement) between levels
        MISS_RESET_MS = 2000  # pause after a miss before re-arming at level 1
        CATCH_HOLD_MS = 2000  # hold the caught laser lit this long so the hit is seen
        CATCH_CUE_DELAY_MS = 250  # gap from the catch zap to the "nice catch" cue

        # Voice / sfx, paths under assets/sounds/effects. The announcements are
        # edge-tts (en-AU-WilliamMultilingualNeural); the level lines double as
        # the "nice catch" feedback. The final-round win reuses Golf's celebration.
        INTRO_SOUND = "catch/intro.wav"
        ZAP_SOUND = "catch/big-zap.wav"  # fires the instant a catch lands
        LEVEL_SOUNDS = (
            "catch/level_1.wav",
            "catch/level_2.wav",
            "catch/level_3.wav",
            "catch/level_4.wav",
        )
        MISS_SOUND = "catch/miss.wav"
        WIN_SOUND = "positive/congrats_extended.wav"  # Golf-style big celebration

        # Looping backing track, streamed from ``assets/music/`` (flat -- no
        # subdirs). Plays on repeat for the whole session and is stopped
        # automatically when Catch exits (state-machine teardown). Optional: if
        # the file is absent or unplayable the game just runs without it.
        #
        # Prefer **OGG Vorbis** -- small like MP3 but loops *gaplessly* under
        # SDL_mixer. MP3 loops with an audible gap (encoder padding SDL does not
        # strip); WAV loops perfectly but is large. Set ``MUSIC = None`` to
        # disable. ``MUSIC_VOL`` is the bed level; ``MUSIC_DUCK_VOL`` is the
        # small dip it drops to *under* a spoken cue (level/miss line) before
        # rising back, so announcements stay clear without silencing the loop.
        MUSIC = "catch_loop.ogg"
        MUSIC_VOL = 0.6
        MUSIC_DUCK_VOL = 0.35

    class WhackAMole:
        """Settings for :class:`~src.programs.whack_a_mole.WhackAMole`."""

        ROUND_MS = 45000  # length of a timed round

        # Port layout: two halves. 1-player uses LEFT only; 2-player uses both,
        # LEFT = player 1 ("black" keys), RIGHT = player 2 ("white" keys). The box
        # can't tell who presses, so sides are socially enforced; spawns alternate
        # to whichever half is "behind" so both get an equal mole count.
        LEFT_PORTS = (0, 1, 2, 3, 4, 5, 6)
        RIGHT_PORTS = (7, 8, 9, 10, 11, 12, 13)

        # Difficulty ramp over the round (linear from *_START at the whistle to
        # *_END at the buzzer). SPAWN_MS is the *per-half* gap between moles -- with
        # both halves in play the box spawns twice as often (alternating sides) so
        # each half sees the same rate as 1-player. LIFETIME_MS is how long a mole
        # stays lit before it times out as a miss.
        SPAWN_MS_START = 1100
        SPAWN_MS_END = 450
        LIFETIME_MS_START = 1500
        LIFETIME_MS_END = 750
        MAX_PER_SIDE = 3  # cap on simultaneous moles per half (2-player)
        # 1-player tops the board up to a freshly rolled target in this range each
        # spawn tick, so the number of moles on screen *varies* (2-player uses the
        # balanced one-per-tick spawn capped by MAX_PER_SIDE and is unaffected).
        SINGLE_MIN_MOLES = 1
        SINGLE_MAX_MOLES = 3

        # Telegraph: blink a mole during the final WARN_MS of its life so a binary
        # laser can still signal "about to vanish".
        WARN_MS = 320
        BLINK_HALF_MS = 80

        # READY prompt: alternately light the black/white halves this long each, to
        # invite "press a black button (1P) / white button (2P)" while the spoken
        # prompt plays.
        PROMPT_HALF_MS = 650

        # --- audio (paths under assets/sounds/effects) ---
        # Fixed clips (22050 Hz / mono / 16-bit): HAMMER plays on every press (the
        # mallet swing), MOLE_HIT only on a successful whack, POPUP on each spawn.
        POPUP = "whack/popup/pop-up.wav"
        HAMMER = "whack/hits/hammer.wav"
        MOLE_HIT = "whack/hits/mole-hit.wav"
        # Spoken stubs -- skipped cleanly if the wav is not present yet (see the
        # README in assets/sounds/effects/whack/ for the lines to record).
        WELCOME = "whack/welcome.wav"            # "black button for one player..."
        RESULT_SINGLE = "whack/result_single.wav"
        P1_WINS = "whack/player_1_wins.wav"
        P2_WINS = "whack/player_2_wins.wav"
        TIE = "whack/tie.wav"
        NEW_HIGHSCORE = "whack/new_highscore.wav"  # solo personal-best beaten
        NEW_RECORD = "whack/new_record.wav"        # 2-player all-time best beaten
        # Spoken end-of-round result readout: "<who> hit N mole(s) and got M
        # miss(es)", composed clip-by-clip (Trivia-style). The lead-ins name the
        # whacker; the count is built from the num/ bank; MOLE/MOLES and the miss
        # words below carry the singular/plural.
        YOU_HIT = "whack/you_hit.wav"              # 1-player: "You hit" + N + mole(s)
        PLAYER_1_HIT = "whack/player_1_hit.wav"    # 2-player: "Player one hit" + N
        PLAYER_2_HIT = "whack/player_2_hit.wav"    # 2-player: "Player two hit" + M
        MOLE_WORD = "whack/mole.wav"               # singular, after a count of 1
        MOLES_WORD = "whack/moles.wav"             # plural, after any other count
        # num/<0..19>.wav + tens num/<20..90>.wav + hundreds num/100.wav,200.wav,
        # composed by _number_clips up to 299 (e.g. 247 = 200 + 40 + 7).
        NUM_DIR = "whack/num"
        # Miss half, appended after the hit count: "and got" then the count then
        # MISS_WORD (1) / MISSES_WORD (2+) -> "...and got three misses". A shutout
        # (zero misses) instead speaks the celebratory PERFECT_GAME on its own.
        PERFECT_GAME = "whack/perfect_game.wav"
        AND_GOT = "whack/and_got.wav"
        MISS_WORD = "whack/miss.wav"
        MISSES_WORD = "whack/misses.wav"
        # Shared assets that already exist in the repo.
        CONGRATS = "positive/congrats_extended.wav"
        FALLBACK_PATCH = "kicks_ascending_mono"  # pitched bonk if mole-hit.wav absent
        MUSIC = "banjo.wav"                      # looping backing track (optional)

        # Persistent score tracker (per-box, not version-controlled). Relative
        # paths are resolved against config.PROJECT_ROOT; an absolute path is used
        # as-is (the headless test points this at a temp file). Holds two records:
        # ``solo_best`` (your single-player personal best) and ``versus_best`` (the
        # highest single-side score ever in a 2-player round).
        HIGHSCORE_PATH = "state/whack_a_mole.json"

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
            7: ("Catch", "catch.wav"),
            8: ("WhackAMole", "whack_a_mole.wav"),
        }

        # --- system power actions (last two physical buttons) ---
        # These do NOT launch a program; they reboot/shut down the box. To guard
        # against accidental triggering they use a three-press confirm flow (see
        # GameSelect): 1st press announces, 2nd press arms (plays ``confirm``),
        # 3rd press executes (plays ``execute`` -- the "doing it now" line).
        # Pressing any other button while armed cancels and returns to the menu
        # (re-arming to that button if it is itself a menu slot).
        # ``announce``/``confirm``/``execute`` are wavs under
        # assets/sounds/effects/menu/ ; ``action`` keys into SYSTEM_ACTIONS.
        SYSTEM_MENU = {
            12: dict(
                action="reboot",
                announce="reboot.wav",
                confirm="reboot_confirm.wav",
                execute="reboot_now.wav",
            ),
            13: dict(
                action="poweroff",
                announce="shutdown.wav",
                confirm="shutdown_confirm.wav",
                execute="shutdown_now.wav",
            ),
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

        # --- volume control (buttons 10/11, GameSelect-only) ---
        # The system-control group alongside the power buttons. Each press is an
        # instant ±10% step of the OS master volume (see :mod:`src.system_volume`);
        # there is no arm/confirm flow. Volume is *menu-only* (like the power
        # slots): during a game buttons 10/11 are ordinary game inputs.
        # button_id -> step direction (+1 = up, -1 = down).
        VOLUME_MENU = {
            10: -1,  # volume down
            11: +1,  # volume up
        }
        # Spoken live-preview confirmations, played at the new level so the loudness
        # itself previews the change (wavs under assets/sounds/effects/menu/).
        VOLUME_UP = "volume_up.wav"
        VOLUME_DOWN = "volume_down.wav"
        VOLUME_MAX = "max_volume.wav"      # spoken when a step lands at 100%
        VOLUME_MUTED = "volume_muted.wav"  # spoken when a step lands at 0%
        # Physical left->right laser order for the volume bar. The two endcap ports
        # (6 and 7) sit at right angles to the in-line bay and are skipped, so the
        # bar is the 12 in-line ports in physical order (matches Golf's ``remap``).
        VOLUME_BAR_PORTS = [0, 13, 1, 12, 2, 11, 3, 10, 4, 9, 5, 8]
        VOLUME_BAR_MS = 1200  # how long the bar stays lit after a press

    class Volume:
        """Settings for the OS-level master volume (see :mod:`src.system_volume`).

        Volume is controlled at the OS layer (PipeWire via ``wpctl``) rather than
        in-app, because pygame has no master gain. The chosen level is persisted
        per-box and re-applied at boot.
        """

        # Persistent, per-box system state (gitignored, not version-controlled).
        # Relative paths resolve against config.PROJECT_ROOT; an absolute path is
        # used as-is (the headless test points this at a temp file). Kept separate
        # from per-game score files (e.g. whack_a_mole.json) because volume is a
        # system-wide setting, not a game record.
        STATE_PATH = "state/system.json"
        DEFAULT = 0.7  # level used on first boot, before any state file exists
        STEP = 0.1     # 10% per button press
        MIN = 0.0
        MAX = 1.0

    class Trivia:
        """Settings for :class:`~src.programs.trivia.Trivia`.

        Two-player face-off: **Black team** (left half, keys 0-6) versus **White
        team** (right half, keys 7-13). Each team buzzes with its endcap button
        and answers on its four choice buttons. Choice *slot* ``i`` (0..3) maps to
        ``BLACK_CHOICES[i]`` / ``WHITE_CHOICES[i]`` so the two halves are mirror
        images (black button 0 == white button 13, etc.).
        """

        # --- match shape ---
        # The match runs until a team reaches TARGET_SCORE -- there is no fixed
        # question count. QUESTIONS_PER_MATCH is now only the size of the question
        # pool to prepare up front (the bank loads its whole pool regardless; this
        # mainly bounds a live OpenTDB fetch), so keep it comfortably above the
        # questions a first-to-TARGET_SCORE race can take.
        TARGET_SCORE = 10  # first team to reach this score wins the match
        QUESTIONS_PER_MATCH = 7  # question pool to prepare (not the match length)
        DIFFICULTY = "any"  # any | easy | medium | hard (OpenTDB filter)
        CATEGORY = None  # None = any; else an OpenTDB category id (int)

        # --- timing (milliseconds) ---
        # FALLBACK choice-selection deadline, used ONLY when the thinking-song
        # asset is missing. Normally the thinking song's own length IS the answer
        # clock (see THINKING_SONG below). Set ONCE per turn, never reset by
        # selecting/re-arming a choice.
        ANSWER_TIMEOUT_MS = 15000
        # Buzz window after the question + choices finish reading. Short and with
        # NO warning (the window is the warning).
        POST_QUESTION_BUZZ_MS = 5000
        VO_GAP_MS = 120  # gap inserted between chained voice-over clips
        READY_REPROMPT_MS = 12000  # re-announce "buzz to begin" if a team stalls

        # --- thinking song (the answer-phase clock) ---
        # Plays once (no loop) the instant an answer window opens -- right after a
        # buzz, and right after a steal re-read -- and serves AS the timer: the
        # answer window lasts exactly the song's length, and running out of song
        # is the lock-in timeout. So author it to the old ANSWER_TIMEOUT_MS above
        # (~15 s). Dropped flat under ``assets/music/``; prefer OGG to save space.
        # Spoken choices gently duck it to THINKING_SONG_DUCK_VOL (Catch-style).
        # Set THINKING_SONG = None to disable (falls back to ANSWER_TIMEOUT_MS).
        THINKING_SONG = "trivia_thinking.ogg"
        THINKING_SONG_VOL = 0.6
        THINKING_SONG_DUCK_VOL = 0.35

        # --- teams (named for the keycap colours on each half of the box) ---
        BLACK_BUZZ = 6  # left endcap
        WHITE_BUZZ = 7  # right endcap
        BLACK_CHOICES = (0, 1, 2, 3)  # choice slot i -> this button id
        WHITE_CHOICES = (13, 12, 11, 10)  # mirror of the black side

        # --- scoring (a team may legitimately sit negative) ---
        SCORE_FIRST_RIGHT = 2  # buzz first and answer correctly
        SCORE_FIRST_WRONG = -1  # buzz first and miss (discourages blind buzzing)
        SCORE_STEAL_RIGHT = 1  # take the steal correctly (you had more info)
        SCORE_STEAL_WRONG = 0  # whiff the steal (no extra penalty)

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
        # WHITELIST: None = draw from the whole bank. Otherwise the name (no
        # extension) of a whitelist file under WHITELIST_DIR; the match still
        # randomly samples QUESTIONS_PER_MATCH distinct questions, but only from
        # that whitelisted subset of the bank. Unlike CURATED_PLAYLIST (a fixed,
        # ordered, predetermined match), a whitelist only narrows the random pool.
        # CURATED_PLAYLIST takes precedence if both are set. Build whitelists with
        # ``tools/trivia_whitelist.py``.
        WHITELIST = "july"
        FETCH_TIMEOUT_S = 3  # OpenTDB request timeout, seconds (live mode)
        # Only relevant if/when a runtime TTS path exists; piper cannot run on the
        # box's ARMv6 Pi Zero W, so PiperVoice is currently a stub.
        PIPER_MODEL = "en_GB-alan-medium"

        # --- asset paths ---
        BANK_PATH = "assets/trivia/bank.json"  # question bank (JSON), repo-relative
        WHITELIST_DIR = "assets/trivia/whitelists"  # named bank-subset whitelists
        EFFECT_DIR = "trivia"  # voice-over root under assets/sounds/effects
