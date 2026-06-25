"""Voice-over for :class:`~src.programs.trivia.Trivia`.

A *voice* turns questions, choices, and scores into playable audio. The game
talks only to the :class:`Voice` interface, so the concrete backend is swappable:

* :class:`PrebakedVoice` -- the working path. Plays per-question wavs baked by
  ``tools/trivia_sync.py`` plus a small set of static lines, all assembled on the
  fly (e.g. a score line = "Black team" + N + "White team" + M).
* :class:`PiperVoice` -- a **stub**. The box is a Pi Zero W (ARMv6) which cannot
  run piper / onnxruntime, so on-device synthesis isn't available; the class
  exists only to keep the seam for a future runtime/cloud TTS.
* :class:`SilentVoice` -- a test double that plays nothing and records calls.

**Interruptibility** is the delicate part and lives in :class:`_VoSequencer`.
Voice-over plays on a *dedicated reserved channel* so it can be cut without
touching one-shot sound effects (the buzz tone keeps playing). A monotonic
generation token guards every scheduled clip advance, so a buzz mid-question
cancels the whole remaining clip sequence atomically -- a stale, already-queued
callback can never resurrect cancelled audio.
"""
from __future__ import annotations

import os
import socket
import sys

import pygame

from ..config import config
from .trivia_source import BankSource, OpenTDBSource, SourceUnavailable


class _VoSequencer:
    """Plays an ordered list of Sounds gaplessly on one channel, interruptibly.

    Args:
        channel: A reserved ``pygame.mixer.Channel`` (or ``None`` to no-op the
            audio, e.g. when the mixer isn't initialised).
        schedule: The owning program's ``after(ms, fn, *args)`` scheduler.
        gap_ms: Silence inserted between consecutive clips.
    """

    def __init__(self, channel, schedule, gap_ms=120):
        self._channel = channel
        self._schedule = schedule
        self._gap_ms = gap_ms
        self._gen = 0           # bumped on every play()/interrupt()
        self._queue: list = []
        self._on_done = None

    def play(self, sounds, on_done=None):
        """Interrupt anything in flight, then play ``sounds`` in order.

        ``on_done`` (if given) is called once, only on *natural* completion of
        the whole sequence -- never when interrupted.
        """
        self.interrupt()
        self._gen += 1
        self._queue = [s for s in sounds if s is not None]
        self._on_done = on_done
        self._advance(self._gen)

    def _advance(self, gen):
        if gen != self._gen:
            return  # a newer play()/interrupt() superseded this scheduled call
        if not self._queue:
            cb, self._on_done = self._on_done, None
            if cb:
                cb()
            return
        sound = self._queue.pop(0)
        dur_ms = self._gap_ms
        if self._channel is not None and sound is not None:
            try:
                self._channel.play(sound)
                dur_ms = int(sound.get_length() * 1000) + self._gap_ms
            except Exception as e:  # pragma: no cover - audio backend dependent
                print(f"[Trivia] VO clip play failed: {e}")
        self._schedule(dur_ms, self._advance, gen)

    def interrupt(self):
        """Stop the current clip and drop the rest of the sequence."""
        self._gen += 1          # invalidate any in-flight _advance(gen)
        self._queue = []
        self._on_done = None
        if self._channel is not None:
            try:
                self._channel.stop()
            except Exception:
                pass

    @property
    def busy(self) -> bool:
        """True while a clip is actively sounding on the channel."""
        return self._channel is not None and bool(self._channel.get_busy())


class Voice:
    """Interface the game uses to speak. See module docstring for backends."""

    def preload(self, questions): ...
    def say_line(self, key, on_done=None): ...
    def say_question(self, question, number=None, on_done=None, with_intro=True,
                     with_choices=False): ...
    def say_choice(self, question, slot, on_done=None): ...
    def say_correct_answer(self, question, on_done=None): ...
    def say_score(self, black, white, on_done=None): ...
    def interrupt(self): ...
    def release(self): ...

    @property
    def busy(self) -> bool:
        return False


class PrebakedVoice(Voice):
    """Plays pre-rendered wavs (edge-tts baked) assembled per utterance.

    Args:
        mixer: The game :class:`~src.audio_utils.Mixer`.
        schedule: The program's ``after`` scheduler (for clip sequencing).
        gap_ms: Inter-clip gap; defaults to ``config.Trivia.VO_GAP_MS``.

    Missing clips are tolerated (logged + skipped to silence) so the game still
    runs before any audio has been baked -- useful for simulator logic checks.
    """

    VO_CHANNEL = 0  # reserved channel index dedicated to voice-over

    # static lines that never depend on question content
    STATIC = {
        "ready_prompt": "vo/both_teams_buzz_to_begin.wav",
        "lets_begin": "vo/both_ready_lets_begin.wav",
        "no_buzz": "vo/no_one_buzzed.wav",
        "five_seconds_remaining": "vo/five_seconds_remaining.wav",
        "correct_answer_is": "vo/the_correct_answer_is.wav",
        "steal_black": "vo/black_team_steal.wav",
        "steal_white": "vo/white_team_steal.wav",
        "black_wins": "vo/black_team_wins.wav",
        "white_wins": "vo/white_team_wins.wav",
        "tie": "vo/its_a_tie.wav",
        "sudden_death": "vo/sudden_death.wav",
        "black_team": "vo/black_team.wav",   # score-line components
        "white_team": "vo/white_team.wav",
        # spoken choice labels read before each option ("A: ...", "B: ...")
        "choice_label_0": "vo/choice_label_a.wav",
        "choice_label_1": "vo/choice_label_b.wav",
        "choice_label_2": "vo/choice_label_c.wav",
        "choice_label_3": "vo/choice_label_d.wav",
    }

    def __init__(self, mixer, schedule, gap_ms=None):
        self.mixer = mixer
        self.dir = config.Trivia.EFFECT_DIR
        gap = config.Trivia.VO_GAP_MS if gap_ms is None else gap_ms
        self.seq = _VoSequencer(self._acquire_channel(), schedule, gap)

    def _acquire_channel(self):
        """Reserve a channel for VO so interrupting it never cuts sfx."""
        try:
            pygame.mixer.set_reserved(self.VO_CHANNEL + 1)
            return pygame.mixer.Channel(self.VO_CHANNEL)
        except Exception as e:  # pragma: no cover - mixer not initialised
            print(f"[Trivia] no reserved VO channel ({e}); VO shares channels")
            return None

    # -- clip resolution ----------------------------------------------------
    def _rel(self, rel):
        return os.path.join(self.dir, rel)

    def _sound(self, rel):
        """Load (tolerantly) and return the Sound for ``rel`` under EFFECT_DIR."""
        path = self._rel(rel)
        try:
            self.mixer.load_effect(path)
            return self.mixer.effects[path]
        except Exception as e:
            print(f"[Trivia] missing VO clip {path!r}: {e}")
            return None

    def _sounds(self, rels):
        return [self._sound(r) for r in rels]

    def _number_clips(self, n):
        """Clip(s) that voice an integer score (handles negatives)."""
        clips = []
        if n < 0:
            clips.append("num/minus.wav")
        clips.append(f"num/{abs(n)}.wav")
        return clips

    def _q_clip(self, question, name):
        return f"q/{question.id}/{name}.wav"

    # -- speech -------------------------------------------------------------
    def preload(self, questions):
        """Warm the Sound cache for a match's questions (best effort)."""
        for q in questions:
            rels = [self._q_clip(q, "question")]
            rels += [self._q_clip(q, f"choice{i}") for i in range(len(q.choices))]
            self._sounds(rels)

    def say_line(self, key, on_done=None):
        self.seq.play(self._sounds([self.STATIC[key]]), on_done)

    def say_question(self, question, number=None, on_done=None, with_intro=True,
                     with_choices=False):
        rels = []
        if with_intro and number is not None:
            rels.append(f"vo/question_{number}.wav")
        rels.append(self._q_clip(question, "question"))
        if with_choices:
            # read each option after its spoken letter: "A: ...", "B: ...", etc.
            for i in range(len(question.choices)):
                rels.append(self.STATIC[f"choice_label_{i}"])
                rels.append(self._q_clip(question, f"choice{i}"))
        self.seq.play(self._sounds(rels), on_done)

    def say_choice(self, question, slot, on_done=None):
        self.seq.play(self._sounds([self._q_clip(question, f"choice{slot}")]), on_done)

    def say_correct_answer(self, question, on_done=None):
        rels = [self.STATIC["correct_answer_is"],
                self._q_clip(question, f"choice{question.correct_index}")]
        self.seq.play(self._sounds(rels), on_done)

    def say_score(self, black, white, on_done=None):
        rels = ([self.STATIC["black_team"]] + self._number_clips(black)
                + [self.STATIC["white_team"]] + self._number_clips(white))
        self.seq.play(self._sounds(rels), on_done)

    def interrupt(self):
        self.seq.interrupt()

    def release(self):
        """Return the reserved VO channel to the auto-allocator on teardown."""
        try:
            pygame.mixer.set_reserved(0)
        except Exception:
            pass

    @property
    def busy(self):
        return self.seq.busy


class PiperVoice(Voice):
    """STUB. On-device piper TTS is not viable on the box (ARMv6 Pi Zero W).

    Piper's prebuilt binaries target armv7l/aarch64/x86_64 only, and ``piper-tts``
    needs onnxruntime, which has no 32-bit-ARM wheels. This class is a placeholder
    so the live/synth seam stays clean for a future runtime or cloud TTS; the
    selection probe never chooses it (see :func:`available`).
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "PiperVoice is a stub: the box's ARMv6 Pi Zero W cannot run piper/"
            "onnxruntime. Use PrebakedVoice, or wire a cloud TTS behind this seam.")

    @staticmethod
    def available() -> bool:
        return False


class SilentVoice(Voice):
    """Test double: plays nothing, records calls, fires ``on_done`` immediately."""

    def __init__(self):
        self.calls = []
        self.interrupts = 0

    def _record(self, tag, on_done):
        self.calls.append(tag)
        if on_done:
            on_done()

    def preload(self, questions):
        self.calls.append(("preload", len(list(questions))))

    def say_line(self, key, on_done=None):
        self._record(("line", key), on_done)

    def say_question(self, question, number=None, on_done=None, with_intro=True,
                     with_choices=False):
        self._record(("question", question.id, number, with_intro, with_choices),
                     on_done)

    def say_choice(self, question, slot, on_done=None):
        self._record(("choice", question.id, slot), on_done)

    def say_correct_answer(self, question, on_done=None):
        self._record(("answer", question.id), on_done)

    def say_score(self, black, white, on_done=None):
        self._record(("score", black, white), on_done)

    def interrupt(self):
        self.interrupts += 1


# --- backend selection -----------------------------------------------------

def _simulated() -> bool:
    return "-s" in sys.argv


def _network_reachable(host="opentdb.com", port=443, timeout=1.0) -> bool:
    """Quick connectivity probe. Always False under the simulator (``-s``)."""
    if _simulated():
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _prebaked_available() -> bool:
    """True if the bank exists (prebaked audio is keyed off bank questions)."""
    return os.path.exists(os.path.join(config.PROJECT_ROOT, config.Trivia.BANK_PATH))


def _make_source(kind, rng=None):
    if kind == "live":
        return OpenTDBSource(config.Trivia.QUESTIONS_PER_MATCH,
                             difficulty=config.Trivia.DIFFICULTY,
                             category=config.Trivia.CATEGORY, rng=rng)
    return BankSource(config.Trivia.QUESTIONS_PER_MATCH,
                      playlist=config.Trivia.CURATED_PLAYLIST,
                      whitelist=config.Trivia.WHITELIST, rng=rng)


def _make_voice(kind, mixer, schedule):
    if kind == "piper" and PiperVoice.available():
        return PiperVoice(mixer, schedule)
    # piper unavailable (always, on this box) or prebaked requested -> prebaked
    return PrebakedVoice(mixer, schedule)


def select_source_and_voice(mixer, schedule, rng=None):
    """Pick the (source, voice) pair for a match.

    Honors ``config.Trivia.FORCE_MODE`` if set; otherwise auto-detects. The
    impossible combo (live questions + prebaked audio) is corrected to the bank,
    and a live source that fails to :meth:`~...QuestionSource.prepare` is the
    caller's cue to fall back -- but we also pre-empt it here by only choosing
    ``live`` when the network is reachable and a runtime voice exists.

    Returns:
        tuple: ``(QuestionSource, Voice)``.
    """
    forced = config.Trivia.FORCE_MODE
    if forced:
        src_kind, voice_kind = forced
        if src_kind == "live" and voice_kind == "prebaked":
            print("[Trivia] FORCE_MODE (live, prebaked) is impossible; "
                  "using (bank, prebaked)")
            src_kind = "bank"
        return _make_source(src_kind, rng), _make_voice(voice_kind, mixer, schedule)

    # auto: live needs both connectivity and a runtime voice (piper). On this
    # box piper is unavailable, so this resolves to bank + prebaked in practice.
    if _network_reachable() and PiperVoice.available():
        return _make_source("live", rng), _make_voice("piper", mixer, schedule)
    return _make_source("bank", rng), _make_voice("prebaked", mixer, schedule)
