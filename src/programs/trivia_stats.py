"""Persistent ask-counts for :class:`~src.programs.trivia.Trivia` selection.

Tracks how many times each trivia question (keyed by its stable
:attr:`~src.programs.trivia_source.Question.id`) has been *asked*, in a small
JSON state file under ``state/`` (gitignored, per-box). The point is to let
:class:`~src.programs.trivia_source.BankSource` favour the least-asked questions
so that, across plays and across reboots, the box works through its whole bank
before any question repeats -- hearing a duplicate stays rare even though each
match's order is still randomised.

The file is a flat ``{question_id: times_asked}`` map. It is **sparse**: a
question absent from the file has been asked zero times, so a freshly grown bank
automatically favours its new questions (count 0) with no migration step.
"""
from __future__ import annotations

import json
import os

from ..config import config


class AskCounts:
    """Loads, queries, orders by, and records trivia question ask-counts.

    Args:
        path: State-file path. Relative paths resolve against
            :data:`config.PROJECT_ROOT`; defaults to
            :data:`config.Trivia.ASK_COUNTS_PATH`. Passing an explicit path lets
            tests point at a throwaway file instead of the real per-box state.
    """

    def __init__(self, path: str | None = None):
        path = path or config.Trivia.ASK_COUNTS_PATH
        self.path = (path if os.path.isabs(path)
                     else os.path.join(config.PROJECT_ROOT, path))
        self._counts = self._load()

    # -- persistence --------------------------------------------------------
    def _load(self) -> dict:
        """Read the saved counts, tolerating a missing or corrupt file.

        Any read/parse error just starts fresh (empty), so a first run -- or a
        truncated file from a power cut -- simply has no history yet rather than
        crashing the game.
        """
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        # keep only well-formed integer counts; ignore anything malformed
        clean = {}
        for key, value in data.items():
            if isinstance(value, bool):
                continue  # bool is an int subclass -- not a count
            if isinstance(value, int):
                clean[str(key)] = value
        return clean

    def _save(self) -> None:
        """Persist the counts atomically (temp file + replace), best effort.

        The atomic replace means a power cut mid-write can never truncate the
        file to garbage and silently wipe every count: a reader sees either the
        whole old file or the whole new one. Any failure is swallowed (logged) --
        losing a single increment is never worth crashing a game over.
        """
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._counts, fh)
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"[Trivia] could not save ask-counts: {e}")

    # -- query / record -----------------------------------------------------
    def get(self, qid: str) -> int:
        """How many times question ``qid`` has been asked (0 if never)."""
        return self._counts.get(qid, 0)

    def record_asked(self, qid: str) -> None:
        """Increment ``qid``'s ask-count and persist immediately.

        Persisting per question (rather than once at match end) is deliberate: a
        match cut short -- a reboot, a power loss, an early return to the menu --
        still leaves every question it *did* ask counted. That per-question
        durability is exactly what the across-reboots selection relies on.
        """
        self._counts[qid] = self.get(qid) + 1
        self._save()

    def order_least_asked(self, questions, rng):
        """Return ``questions`` ordered least-asked-first, ties broken randomly.

        This is a persistent "shuffle bag": sorting by ask-count makes the match
        draw from the least-asked tier first, while the random tiebreak keeps the
        order within a tier (and so across equal-count sessions) fresh. Drawing
        from the front of this order works through the entire pool before any
        question is asked a second time, so duplicates only appear once every
        question has been heard at least once.

        Args:
            questions: The candidate pool (each must expose a stable ``id``).
            rng: Random source for the in-tier tiebreak (injectable for tests).

        Returns:
            A new list of the same questions, least-asked first.
        """
        return sorted(questions, key=lambda q: (self.get(q.id), rng.random()))
