"""Headless logic test for Trivia bank whitelists.

A whitelist narrows the random draw to a named subset of the bank without pinning
the questions (unlike a curated playlist). This exercises:

* :class:`BankSource` filtering to a whitelist (by name *and* by explicit ids),
* the random sample staying inside the subset and ``match_length`` capping at it,
* a playlist taking precedence over a whitelist,
* :func:`load_whitelist` reading the on-disk JSON, and
* the ``tools/trivia_whitelist.py`` ``resolve_spec`` selection grammar.

It points ``config.PROJECT_ROOT`` at a temp dir with a synthetic bank, so it never
touches the real assets. Run from repo root:

    python3 scratch/test_whitelist.py
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config
from src.programs import trivia_source
from src.programs.trivia_source import BankSource, SourceUnavailable, load_whitelist
from tools.trivia_whitelist import resolve_spec, load_bank


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label)


def q(qid, category, difficulty="easy"):
    return {"id": qid, "category": category, "difficulty": difficulty,
            "question": f"{qid}?", "choices": ["a", "b", "c", "d"],
            "correct_index": 0}


BANK = [
    q("geo-1", "Geography"), q("geo-2", "Geography"), q("geo-3", "Geography"),
    q("sci-1", "Science", "hard"), q("sci-2", "Science", "medium"),
    q("his-1", "History"), q("his-2", "History"),
]


def main():
    tmp = tempfile.mkdtemp(prefix="trivia-wl-")
    os.makedirs(os.path.join(tmp, "whitelists"), exist_ok=True)
    with open(os.path.join(tmp, "bank.json"), "w") as fh:
        json.dump({"questions": BANK}, fh)
    with open(os.path.join(tmp, "whitelists", "geo.json"), "w") as fh:
        json.dump({"name": "geo", "description": "geography only",
                   "ids": ["geo-1", "geo-2", "geo-3"]}, fh)
    with open(os.path.join(tmp, "whitelists", "empty.json"), "w") as fh:
        json.dump({"name": "empty", "ids": ["nope-1", "nope-2"]}, fh)

    # Repoint path resolution at the temp bank/whitelists.
    saved = (config.PROJECT_ROOT, config.Trivia.BANK_PATH, config.Trivia.WHITELIST_DIR)
    config.PROJECT_ROOT = tmp
    config.Trivia.BANK_PATH = "bank.json"
    config.Trivia.WHITELIST_DIR = "whitelists"
    # the tool caches paths at import; point them at the temp dir too
    trivia_whitelist = sys.modules["tools.trivia_whitelist"]
    trivia_whitelist.BANK_PATH = os.path.join(tmp, "bank.json")
    trivia_whitelist.WHITELIST_DIR = os.path.join(tmp, "whitelists")
    try:
        geo_ids = {"geo-1", "geo-2", "geo-3"}

        # load_whitelist reads the ids off disk.
        check("load_whitelist returns the file's ids",
              set(load_whitelist("geo")) == geo_ids)
        try:
            load_whitelist("missing")
            check("load_whitelist raises on a missing file", False)
        except SourceUnavailable:
            check("load_whitelist raises on a missing file", True)

        # BankSource by whitelist name: draw is confined to the subset.
        src = BankSource(2, whitelist="geo", rng=random.Random(1))
        src.prepare()
        drawn = []
        while True:
            nq = src.next_question()
            if nq is None:
                break
            drawn.append(nq.id)
        check("named whitelist: every drawn id is in the subset",
              set(drawn) <= geo_ids)
        check("named whitelist: match_length capped at count (2)", src.match_length == 2)
        check("named whitelist: extras still queued for sudden-death (all 3)",
              len(drawn) == 3)

        # match_length caps at the subset size when count exceeds it.
        src = BankSource(10, whitelist="geo", rng=random.Random(2))
        src.prepare()
        check("named whitelist: match_length caps at subset size (3)",
              src.match_length == 3)

        # whitelist as an explicit iterable of ids (no file).
        src = BankSource(5, whitelist=["sci-1", "sci-2"], rng=random.Random(3))
        src.prepare()
        ids = set()
        while (nq := src.next_question()) is not None:
            ids.add(nq.id)
        check("explicit-id whitelist filters to exactly those ids",
              ids == {"sci-1", "sci-2"})

        # an empty match raises so the caller can fall back.
        try:
            BankSource(3, whitelist="empty", rng=random.Random(4)).prepare()
            check("whitelist matching zero bank questions raises", False)
        except SourceUnavailable:
            check("whitelist matching zero bank questions raises", True)

        # playlist wins over whitelist when both are set.
        src = BankSource(3, playlist=["his-1", "his-2"], whitelist="geo",
                         rng=random.Random(5))
        src.prepare()
        first_two = [src.next_question().id, src.next_question().id]
        check("playlist takes precedence over whitelist", first_two == ["his-1", "his-2"])

        # no whitelist: the whole bank is in play.
        src = BankSource(99, rng=random.Random(6))
        src.prepare()
        check("no whitelist: full bank match_length", src.match_length == len(BANK))

        # --- tool's selection-spec grammar -------------------------------
        bank = load_bank()  # Questions, in file order
        check("resolve_spec 'all' selects everything", resolve_spec("all", bank) ==
              {b.id for b in bank})
        check("resolve_spec index", resolve_spec("0", bank) == {"geo-1"})
        check("resolve_spec range", resolve_spec("0-2", bank) == {"geo-1", "geo-2", "geo-3"})
        check("resolve_spec cat: substring (case-insensitive)",
              resolve_spec("cat:geo", bank) == geo_ids)
        check("resolve_spec diff:hard", resolve_spec("diff:hard", bank) == {"sci-1"})
        check("resolve_spec literal id", resolve_spec("his-2", bank) == {"his-2"})
        check("resolve_spec out-of-range index -> empty", resolve_spec("99", bank) == set())
    finally:
        config.PROJECT_ROOT, config.Trivia.BANK_PATH, config.Trivia.WHITELIST_DIR = saved

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
