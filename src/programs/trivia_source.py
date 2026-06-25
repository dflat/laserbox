"""Question sources for :class:`~src.programs.trivia.Trivia`.

A *source* is the thing that hands the game one :class:`Question` at a time. Two
concrete sources implement the same small contract so the game never knows which
is wired in:

* :class:`BankSource` -- reads a local JSON bank (``assets/trivia/bank.json``).
  Samples ``count`` distinct questions at random; a ``whitelist`` first narrows
  the pool to a named subset of the bank, while a ``playlist`` instead plays an
  exact curated list in order (playlist wins if both are given).
* :class:`OpenTDBSource` -- fetches a batch from the Open Trivia DB over HTTP.

Everything is decided up front in :meth:`QuestionSource.prepare` (one batch
fetch / one sample), so a mid-match network drop can never strand a round. A
failed live fetch raises :class:`SourceUnavailable` and the caller falls back to
the bank.

The :class:`Question` value type is identical regardless of origin: its choices
are stored in a **frozen, already-shuffled order** with ``correct_index`` into
that order, so a question's on-disk audio (one clip per choice slot) always lines
up with the buttons.
"""
from __future__ import annotations

import abc
import hashlib
import html
import json
import os
import random
from collections import deque
from dataclasses import dataclass

from ..config import config


class SourceUnavailable(Exception):
    """Raised by :meth:`QuestionSource.prepare` when a source can't be used.

    The caller treats this as "try the next source" (e.g. live -> bank).
    """


def load_whitelist(name: str, whitelist_dir: str | None = None) -> list[str]:
    """Load a named bank-subset whitelist and return its question ids.

    A whitelist is a small JSON file (built by ``tools/trivia_whitelist.py``)
    under :data:`config.Trivia.WHITELIST_DIR` that narrows which bank questions a
    match may draw from. Accepts either a ``{"ids": [...]}`` object (the format the
    tool writes) or a bare JSON list of ids.

    Args:
        name: Whitelist file name without the ``.json`` extension.
        whitelist_dir: Repo-relative directory to look in (defaults to
            :data:`config.Trivia.WHITELIST_DIR`).

    Returns:
        The list of bank question ids in the whitelist.

    Raises:
        SourceUnavailable: If the file is missing or has no usable ids.
    """
    wdir = whitelist_dir or config.Trivia.WHITELIST_DIR
    path = os.path.join(config.PROJECT_ROOT, wdir, f"{name}.json")
    if not os.path.exists(path):
        raise SourceUnavailable(f"whitelist not found: {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    ids = data.get("ids") if isinstance(data, dict) else data
    if not ids:
        raise SourceUnavailable(f"whitelist {name!r} contains no ids")
    return list(ids)


@dataclass(frozen=True)
class Question:
    """One multiple-choice question with a fixed choice ordering.

    Attributes:
        id: Stable short hash of the question text -- the dedup key and the
            audio-folder name (``assets/sounds/effects/trivia/q/<id>/``).
        category: Free-text category (may be empty).
        difficulty: ``"easy"`` / ``"medium"`` / ``"hard"`` (may be empty).
        question: The question prompt.
        choices: Exactly four option strings, in their **frozen** display order.
        correct_index: Index (0..3) of the correct option within ``choices``.
    """

    id: str
    category: str
    difficulty: str
    question: str
    choices: tuple
    correct_index: int

    @property
    def correct_choice(self) -> str:
        """The text of the correct option."""
        return self.choices[self.correct_index]

    @staticmethod
    def make_id(question_text: str) -> str:
        """Stable 8-hex-char id derived from the question text."""
        return hashlib.sha1(question_text.encode("utf-8")).hexdigest()[:8]

    @classmethod
    def from_opentdb(cls, raw: dict, rng: random.Random | None = None) -> "Question":
        """Build a Question from one OpenTDB ``results`` entry.

        Unescapes HTML entities (OpenTDB returns ``&quot;`` etc.), combines the
        correct + incorrect answers, and freezes a single random shuffle. The
        correct option is tracked by identity through the shuffle so duplicate
        option text can't mislabel the answer.

        Args:
            raw: One element of the OpenTDB ``results`` list.
            rng: Random source (injectable for deterministic tests).
        """
        rng = rng or random
        question = html.unescape(raw["question"])
        correct = html.unescape(raw["correct_answer"])
        # tag each option with whether it is the correct one, then shuffle pairs
        options = [(html.unescape(c), False) for c in raw["incorrect_answers"]]
        options.append((correct, True))
        rng.shuffle(options)
        choices = tuple(text for text, _ in options)
        correct_index = next(i for i, (_, ok) in enumerate(options) if ok)
        return cls(
            id=cls.make_id(question),
            category=html.unescape(raw.get("category", "")),
            difficulty=raw.get("difficulty", ""),
            question=question,
            choices=choices,
            correct_index=correct_index,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        """Build a Question from a bank JSON record."""
        return cls(
            id=d["id"],
            category=d.get("category", ""),
            difficulty=d.get("difficulty", ""),
            question=d["question"],
            choices=tuple(d["choices"]),
            correct_index=d["correct_index"],
        )

    def to_dict(self) -> dict:
        """Serialise to a bank JSON record (choices as a list)."""
        return {
            "id": self.id,
            "category": self.category,
            "difficulty": self.difficulty,
            "question": self.question,
            "choices": list(self.choices),
            "correct_index": self.correct_index,
        }


class QuestionSource(abc.ABC):
    """Common contract: prepare a match's questions, then pull them one by one.

    Args:
        count: How many questions the match wants. The actual match length ends
            up in :attr:`match_length` after :meth:`prepare` (a curated playlist
            or a short bank can change it).
    """

    def __init__(self, count: int):
        self.count = count
        self.match_length = count
        self._remaining: deque[Question] = deque()

    @abc.abstractmethod
    def prepare(self) -> None:
        """Populate the question pool. Raise :class:`SourceUnavailable` on failure."""

    def next_question(self) -> Question | None:
        """Pop the next question, or ``None`` once the pool is exhausted."""
        return self._remaining.popleft() if self._remaining else None

    def has_next(self) -> bool:
        """True while questions remain (including the sudden-death buffer)."""
        return bool(self._remaining)


class BankSource(QuestionSource):
    """Reads questions from the local JSON bank.

    Default: shuffles the whole bank and pulls ``count`` for the match (extras stay
    available for sudden-death). With a ``whitelist``: the same random draw, but
    restricted first to the whitelisted subset of bank questions. With a
    ``playlist``: plays exactly those questions in order, then any leftover bank
    questions (shuffled) back the sudden-death rounds. A playlist takes precedence
    over a whitelist if both are supplied.

    Args:
        count: Desired match length (ignored when a playlist is given).
        bank_path: Repo-relative path to the bank JSON.
        playlist: Optional ordered list of question ids (str) or bank indices
            (int) for a curated "determined" match.
        whitelist: Optional bank-subset filter -- either a whitelist *name* (str,
            resolved against :data:`config.Trivia.WHITELIST_DIR`) or an explicit
            iterable of question ids. The match still randomly samples ``count``
            distinct questions, only from this subset.
        rng: Random source (injectable for deterministic tests).
    """

    def __init__(self, count, bank_path=None, playlist=None, whitelist=None, rng=None):
        super().__init__(count)
        self.bank_path = bank_path or config.Trivia.BANK_PATH
        self.playlist = playlist
        self.whitelist = whitelist
        self.rng = rng or random

    def prepare(self) -> None:
        questions = self._load_bank()
        if not questions:
            raise SourceUnavailable(f"empty or missing trivia bank: {self.bank_path}")
        if self.playlist:
            chosen = self._resolve_playlist(questions)
            if not chosen:
                raise SourceUnavailable("curated playlist resolved to zero questions")
            used = {q.id for q in chosen}
            extra = [q for q in questions if q.id not in used]
            self.rng.shuffle(extra)
            self.match_length = len(chosen)
            self._remaining = deque(chosen + extra)
        else:
            questions = self._apply_whitelist(questions)
            self.rng.shuffle(questions)
            self.match_length = min(self.count, len(questions))
            self._remaining = deque(questions)

    def _apply_whitelist(self, questions: list[Question]) -> list[Question]:
        """Narrow ``questions`` to the configured whitelist (no-op if unset)."""
        if not self.whitelist:
            return questions
        ids = (load_whitelist(self.whitelist) if isinstance(self.whitelist, str)
               else list(self.whitelist))
        allowed = set(ids)
        filtered = [q for q in questions if q.id in allowed]
        if not filtered:
            raise SourceUnavailable(
                f"whitelist {self.whitelist!r} matched zero bank questions")
        return filtered

    def _bank_abspath(self) -> str:
        # mirrors Mixer's PROJECT_ROOT-relative convention so cwd is the repo dir
        return os.path.join(config.PROJECT_ROOT, self.bank_path)

    def _load_bank(self) -> list[Question]:
        path = self._bank_abspath()
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        records = data["questions"] if isinstance(data, dict) else data
        return [Question.from_dict(r) for r in records]

    def _resolve_playlist(self, questions: list[Question]) -> list[Question]:
        by_id = {q.id: q for q in questions}
        chosen: list[Question] = []
        for entry in self.playlist:
            if isinstance(entry, int):
                if 0 <= entry < len(questions):
                    chosen.append(questions[entry])
                else:
                    print(f"[Trivia] curated index {entry} out of range; skipped")
            elif entry in by_id:
                chosen.append(by_id[entry])
            else:
                print(f"[Trivia] curated id {entry!r} not in bank; skipped")
        return chosen


class OpenTDBSource(QuestionSource):
    """Fetches a batch of multiple-choice questions from the Open Trivia DB.

    The whole match (plus a small sudden-death buffer) is fetched in one request
    during :meth:`prepare`; nothing touches the network afterwards. Any failure
    -- no connectivity, timeout, bad response code, empty result -- raises
    :class:`SourceUnavailable` so the caller can fall back to the bank.

    Args:
        count: Desired match length.
        difficulty: ``any`` / ``easy`` / ``medium`` / ``hard``.
        category: Optional OpenTDB category id.
        timeout: Per-request timeout in seconds.
        rng: Random source for the per-question choice shuffle.
    """

    API = "https://opentdb.com/api.php"
    MAX_AMOUNT = 50            # OpenTDB hard cap per request
    SUDDEN_DEATH_BUFFER = 5    # extra questions fetched to back tie-breakers
    _DIFFICULTIES = {"easy", "medium", "hard"}

    def __init__(self, count, difficulty="any", category=None, timeout=None, rng=None):
        super().__init__(count)
        self.difficulty = difficulty
        self.category = category
        self.timeout = timeout if timeout is not None else config.Trivia.FETCH_TIMEOUT_S
        self.rng = rng or random

    def prepare(self) -> None:
        # `requests` is imported lazily: the live source is optional, and the
        # box's runtime path is bank-only, so importing it must not be required.
        try:
            import requests
        except ImportError as e:  # pragma: no cover - environment dependent
            raise SourceUnavailable("requests not installed") from e

        amount = min(self.count + self.SUDDEN_DEATH_BUFFER, self.MAX_AMOUNT)
        params = {"amount": amount, "type": "multiple"}
        if self.difficulty in self._DIFFICULTIES:
            params["difficulty"] = self.difficulty
        if self.category:
            params["category"] = self.category
        try:
            resp = requests.get(self.API, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise SourceUnavailable(f"OpenTDB fetch failed: {e}") from e

        if data.get("response_code") != 0 or not data.get("results"):
            raise SourceUnavailable(
                f"OpenTDB response_code={data.get('response_code')}")

        questions = [Question.from_opentdb(raw, self.rng) for raw in data["results"]]
        self.match_length = min(self.count, len(questions))
        self._remaining = deque(questions)
