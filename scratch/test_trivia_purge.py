"""Headless test for ``tools/trivia_sync.py --purge``.

Builds a throwaway bank + audio folders + whitelists in a temp dir, points the
tool's module globals at them, and checks that a purge keeps exactly the ids
referenced by a whitelist or CURATED_PLAYLIST and deletes the rest (bank records,
baked audio folders, and orphan audio with no bank record). Also checks the
safety rail that refuses to wipe everything when nothing is referenced.

Run from repo root:

    python3 scratch/test_trivia_purge.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.trivia_sync as ts
from src.config import config


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label)


def q(qid):
    return {"id": qid, "category": "C", "difficulty": "easy",
            "question": f"{qid}?", "choices": ["a", "b", "c", "d"],
            "correct_index": 0}


def setup(tmp, bank_ids, audio_ids, whitelists, note="keepme"):
    """Lay down a bank, audio folders, and whitelist files under ``tmp``."""
    os.makedirs(os.path.join(tmp, "whitelists"), exist_ok=True)
    audio_root = os.path.join(tmp, "effects", "trivia", "q")
    os.makedirs(audio_root, exist_ok=True)
    with open(os.path.join(tmp, "bank.json"), "w") as fh:
        json.dump({"questions": [q(i) for i in bank_ids], "_note": note}, fh)
    for aid in audio_ids:
        os.makedirs(os.path.join(audio_root, aid), exist_ok=True)
        with open(os.path.join(audio_root, aid, "question.wav"), "w") as fh:
            fh.write("x")  # stand-in for a baked clip
    for name, ids in whitelists.items():
        with open(os.path.join(tmp, "whitelists", f"{name}.json"), "w") as fh:
            json.dump({"name": name, "ids": ids}, fh)
    # repoint the tool at the temp tree
    ts.BANK_PATH = os.path.join(tmp, "bank.json")
    ts.WHITELIST_DIR = os.path.join(tmp, "whitelists")
    ts.Q_AUDIO_DIR = audio_root
    return audio_root


def bank_ids_now():
    return [r["id"] for r in ts.load_bank()]


def audio_dirs_now(audio_root):
    return sorted(d for d in os.listdir(audio_root)
                  if os.path.isdir(os.path.join(audio_root, d)))


def main():
    saved_playlist = config.Trivia.CURATED_PLAYLIST
    saved_globals = (ts.BANK_PATH, ts.WHITELIST_DIR, ts.Q_AUDIO_DIR)
    try:
        # === Case 1: whitelist + curated playlist define what survives ======
        tmp = tempfile.mkdtemp(prefix="purge-1-")
        # bank q1..q5; audio for q1..q5 plus an orphan q9 (no bank record)
        audio_root = setup(tmp,
                           bank_ids=["q1", "q2", "q3", "q4", "q5"],
                           audio_ids=["q1", "q2", "q3", "q4", "q5", "q9"],
                           whitelists={"wl": ["q1", "q2"]})
        config.Trivia.CURATED_PLAYLIST = ["q3"]   # plus q3 via the curated list
        ts.do_purge(yes=True, allow_empty=False)

        kept_bank = bank_ids_now()
        kept_audio = audio_dirs_now(audio_root)
        check("bank keeps exactly the referenced ids (q1,q2,q3)",
              kept_bank == ["q1", "q2", "q3"])
        check("audio keeps exactly the referenced ids (q1,q2,q3)",
              kept_audio == ["q1", "q2", "q3"])
        check("unreferenced bank questions purged (q4,q5 gone)",
              "q4" not in kept_bank and "q5" not in kept_bank)
        check("orphan audio with no bank record purged (q9 gone)",
              "q9" not in kept_audio)
        with open(ts.BANK_PATH) as fh:
            check("bank _note preserved", json.load(fh).get("_note") == "keepme")

        # === Case 2: curated playlist by positional index ===================
        tmp = tempfile.mkdtemp(prefix="purge-2-")
        audio_root = setup(tmp,
                           bank_ids=["a", "b", "c"],
                           audio_ids=["a", "b", "c"],
                           whitelists={})            # no whitelists
        config.Trivia.CURATED_PLAYLIST = [0, 2]      # -> ids "a" and "c"
        ts.do_purge(yes=True, allow_empty=False)
        check("playlist positional indices resolve to ids (keep a,c)",
              bank_ids_now() == ["a", "c"])
        check("index-referenced audio kept (a,c); b removed",
              audio_dirs_now(audio_root) == ["a", "c"])

        # === Case 3: nothing referenced -> refuse (don't wipe everything) ===
        tmp = tempfile.mkdtemp(prefix="purge-3-")
        audio_root = setup(tmp,
                           bank_ids=["x", "y"],
                           audio_ids=["x", "y"],
                           whitelists={})
        config.Trivia.CURATED_PLAYLIST = None
        try:
            ts.do_purge(yes=True, allow_empty=False)
            check("empty references refuses to purge (raises SystemExit)", False)
        except SystemExit:
            check("empty references refuses to purge (raises SystemExit)", True)
        check("refused purge left the bank untouched", bank_ids_now() == ["x", "y"])

        # === Case 4: nothing to do when everything is referenced ============
        tmp = tempfile.mkdtemp(prefix="purge-4-")
        audio_root = setup(tmp,
                           bank_ids=["m", "n"],
                           audio_ids=["m", "n"],
                           whitelists={"all": ["m", "n"]})
        config.Trivia.CURATED_PLAYLIST = None
        ts.do_purge(yes=True, allow_empty=False)
        check("fully-referenced bank is left intact", bank_ids_now() == ["m", "n"])
        check("fully-referenced audio is left intact",
              audio_dirs_now(audio_root) == ["m", "n"])
    finally:
        config.Trivia.CURATED_PLAYLIST = saved_playlist
        ts.BANK_PATH, ts.WHITELIST_DIR, ts.Q_AUDIO_DIR = saved_globals

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
