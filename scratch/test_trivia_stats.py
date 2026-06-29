"""Headless logic test for persistent trivia ask-counts.

Covers :class:`~src.programs.trivia_stats.AskCounts` and its wiring into
:class:`~src.programs.trivia_source.BankSource`:

* counts load/record/persist across instances (durable across "reboots"),
* a missing or corrupt state file is tolerated (starts fresh),
* ``order_least_asked`` orders least-asked-first, ties broken randomly,
* BankSource draws the least-asked questions first and records each as asked,
* only questions actually *handed out* are counted (not the whole prepared pool),
* across matches the box covers the whole pool before any question repeats,
* a brand-new bank question (no record) is favoured (sparse == count 0),
* with no store wired in, BankSource keeps its old shuffle behaviour and writes
  nothing (so the real per-box state is never touched by tests).

Uses temp files/dirs throughout, so it never reads or writes real assets/state.
Run from repo root:

    python3 scratch/test_trivia_stats.py
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config
from src.programs.trivia_source import BankSource, Question
from src.programs.trivia_stats import AskCounts


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label)


def Q(qid):
    return Question(id=qid, category="", difficulty="", question=f"{qid}?",
                    choices=("a", "b", "c", "d"), correct_index=0)


def q(qid):
    return {"id": qid, "category": "", "difficulty": "",
            "question": f"{qid}?", "choices": ["a", "b", "c", "d"],
            "correct_index": 0}


def drain(src):
    """Pop every question id a source will hand out, in order."""
    out = []
    while (nq := src.next_question()) is not None:
        out.append(nq.id)
    return out


def main():
    tmpdir = tempfile.mkdtemp(prefix="trivia-stats-")

    # === AskCounts: load / record / persist =============================
    path = os.path.join(tmpdir, "counts.json")
    store = AskCounts(path=path)
    check("unknown question counts as zero", store.get("nope") == 0)
    store.record_asked("a")
    store.record_asked("a")
    store.record_asked("b")
    check("record increments per call", store.get("a") == 2 and store.get("b") == 1)

    reloaded = AskCounts(path=path)  # a fresh process / a reboot
    check("counts persist across instances (across reboots)",
          reloaded.get("a") == 2 and reloaded.get("b") == 1)
    with open(path) as fh:
        check("on-disk file is a flat {id: count} map",
              json.load(fh) == {"a": 2, "b": 1})

    # === AskCounts: tolerant of a missing / corrupt file ================
    check("missing file -> empty store",
          AskCounts(path=os.path.join(tmpdir, "absent.json")).get("a") == 0)
    bad = os.path.join(tmpdir, "corrupt.json")
    with open(bad, "w") as fh:
        fh.write("{ this is not json")
    store_bad = AskCounts(path=bad)
    check("corrupt file -> starts fresh, no crash", store_bad.get("a") == 0)
    store_bad.record_asked("z")  # and it can recover by writing a clean file
    check("corrupt file is overwritten cleanly on next save",
          AskCounts(path=bad).get("z") == 1)

    # === order_least_asked: least-asked first, random in-tier ===========
    s = AskCounts(path=os.path.join(tmpdir, "order.json"))
    s.record_asked("hot"); s.record_asked("hot"); s.record_asked("warm")
    pool = [Q("hot"), Q("warm"), Q("cold1"), Q("cold2")]
    ordered = [x.id for x in s.order_least_asked(pool, random.Random(0))]
    check("least-asked tier (count 0) comes before any asked question",
          set(ordered[:2]) == {"cold1", "cold2"})
    check("within higher counts, lower count precedes higher",
          ordered.index("warm") < ordered.index("hot"))
    # the in-tier order is randomised by the rng, not fixed input order
    seen = {tuple(x.id for x in s.order_least_asked(pool, random.Random(seed))[:2])
            for seed in range(20)}
    check("in-tier order varies with the rng (not always input order)", len(seen) > 1)

    # === BankSource integration: favour least-asked, record on draw =====
    # Point path resolution at a temp bank so we never touch real assets.
    saved = (config.PROJECT_ROOT, config.Trivia.BANK_PATH)
    config.PROJECT_ROOT = tmpdir
    config.Trivia.BANK_PATH = "bank.json"
    try:
        bank_ids = ["q1", "q2", "q3", "q4", "q5", "q6"]
        with open(os.path.join(tmpdir, "bank.json"), "w") as fh:
            json.dump({"questions": [q(i) for i in bank_ids]}, fh)
        counts_path = os.path.join(tmpdir, "bank_counts.json")

        # Match 1: draw a 4-question match from a clean slate.
        m1 = BankSource(4, rng=random.Random(1), ask_counts=AskCounts(counts_path))
        m1.prepare()
        match1 = [m1.next_question().id for _ in range(4)]  # only 4 actually asked
        store_after = AskCounts(counts_path)
        check("only handed-out questions are recorded (4, not the whole pool of 6)",
              sum(store_after.get(i) for i in bank_ids) == 4
              and all(store_after.get(i) == 1 for i in match1))
        unasked = set(bank_ids) - set(match1)
        check("two questions were left unasked after match 1", len(unasked) == 2)

        # Match 2: a fresh store (a reboot) must favour the still-unasked pair.
        m2 = BankSource(4, rng=random.Random(7), ask_counts=AskCounts(counts_path))
        m2.prepare()
        first_two = [m2.next_question().id, m2.next_question().id]
        check("after a reboot, the least-asked questions are drawn first",
              set(first_two) == unasked)
        # match1's 4 + match2's first 2 are 6 *distinct* ids: the whole pool is
        # covered before any question is asked a second time.
        first_six = match1 + first_two
        check("whole pool is covered before any question repeats",
              len(set(first_six)) == 6 and set(first_six) == set(bank_ids))

        # A brand-new bank question (never recorded) is favoured immediately.
        bank_ids.append("q7")
        with open(os.path.join(tmpdir, "bank.json"), "w") as fh:
            json.dump({"questions": [q(i) for i in bank_ids]}, fh)
        m3 = BankSource(1, rng=random.Random(3), ask_counts=AskCounts(counts_path))
        m3.prepare()
        check("a freshly added (count 0) question is favoured over asked ones",
              m3.next_question().id == "q7")

        # No store wired in: old shuffle behaviour, and nothing is persisted.
        sentinel = os.path.join(tmpdir, "should_not_exist.json")
        config.Trivia.ASK_COUNTS_PATH = sentinel  # if anything wrote a default
        plain = BankSource(6, rng=random.Random(4))  # ask_counts defaults to None
        plain.prepare()
        drawn = drain(plain)
        check("no-store draw still returns the whole pool", set(drawn) == set(bank_ids))
        check("no-store source writes no state file at all",
              not os.path.exists(sentinel))
    finally:
        config.PROJECT_ROOT, config.Trivia.BANK_PATH = saved

    print()
    if all(passed):
        print(f"ALL {len(passed)} CHECKS PASSED")
        return 0
    print(f"{passed.count(False)} / {len(passed)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
