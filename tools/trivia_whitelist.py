#!/usr/bin/env python3
"""Interactively build a Trivia *bank whitelist* (dev/desktop tool).

A whitelist is a named subset of the question bank. Unlike a curated playlist
(``config.Trivia.CURATED_PLAYLIST`` -- a fixed, ordered, predetermined match),
a whitelist does **not** pin the questions: a match still randomly samples
``QUESTIONS_PER_MATCH`` distinct questions, it just draws them only from the
whitelisted pool. Point the game at one by setting ``config.Trivia.WHITELIST`` to
the whitelist's name.

Whitelists are saved as JSON under ``assets/trivia/whitelists/<name>.json``::

    {"name": "...", "description": "...", "ids": ["geo-aus-capital", ...]}

Run it (no audio/tools needed -- it only reads the bank and writes JSON)::

    python tools/trivia_whitelist.py                 # start a new whitelist
    python tools/trivia_whitelist.py --edit easy     # load + edit an existing one

It drops you in a small REPL. ``help`` lists the commands; the gist is:

* ``cats`` / ``list [filter]`` -- browse the bank (filter = a category substring,
  ``sel`` for selected only, or ``unsel`` for the rest).
* ``add <spec>`` / ``rm <spec>`` / ``toggle <spec>`` -- change the selection,
  where ``<spec>`` is ``all``, an index ``5``, a range ``5-9``, a question id,
  ``cat:<text>`` (category substring), or ``diff:<easy|medium|hard>``.
* ``step [filter]`` -- walk the bank one question at a time, answering
  ``y``/``n``/``s``(kip)/``q``(uit) to include each.
* ``name <name>`` / ``desc <text>`` -- set the whitelist's name / description.
* ``save [name]`` -- write it out. ``quit`` exits.
"""
import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.config import config  # noqa: E402
from src.programs.trivia_source import Question  # noqa: E402

BANK_PATH = os.path.join(REPO_ROOT, config.Trivia.BANK_PATH)
WHITELIST_DIR = os.path.join(REPO_ROOT, config.Trivia.WHITELIST_DIR)


# -- bank / whitelist IO ----------------------------------------------------

def load_bank() -> list[Question]:
    """Load the bank as Questions, preserving on-disk order (indices are stable)."""
    if not os.path.exists(BANK_PATH):
        sys.exit(f"no bank at {BANK_PATH}; run tools/trivia_sync.py --fetch first")
    with open(BANK_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    records = data["questions"] if isinstance(data, dict) else data
    return [Question.from_dict(r) for r in records]


def load_whitelist(name: str) -> tuple[str, set[str]]:
    """Return ``(description, ids)`` for an existing whitelist (for --edit)."""
    path = os.path.join(WHITELIST_DIR, f"{name}.json")
    if not os.path.exists(path):
        sys.exit(f"no whitelist at {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data.get("description", ""), set(data.get("ids", []))
    return "", set(data)


def save_whitelist(name: str, description: str, ids: list[str]) -> str:
    """Write ``<WHITELIST_DIR>/<name>.json`` and return its path."""
    os.makedirs(WHITELIST_DIR, exist_ok=True)
    path = os.path.join(WHITELIST_DIR, f"{name}.json")
    payload = {"name": name, "description": description, "ids": ids}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


# -- selection-spec resolution ---------------------------------------------

def resolve_spec(spec: str, bank: list[Question]) -> set[str]:
    """Turn a selection ``spec`` into the set of question ids it names.

    Supported forms (see module docstring): ``all``; an index ``5``; a range
    ``5-9``; a literal question id; ``cat:<substring>``; ``diff:<level>``. Unknown
    or out-of-range specs resolve to the empty set (the caller reports "0").
    """
    spec = spec.strip()
    if not spec:
        return set()
    if spec == "all":
        return {q.id for q in bank}
    if spec.startswith("cat:"):
        needle = spec[4:].strip().lower()
        return {q.id for q in bank if needle in q.category.lower()}
    if spec.startswith("diff:"):
        level = spec[5:].strip().lower()
        return {q.id for q in bank if q.difficulty.lower() == level}
    m = re.fullmatch(r"(\d+)-(\d+)", spec)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {bank[i].id for i in range(lo, hi + 1) if 0 <= i < len(bank)}
    if spec.isdigit():
        i = int(spec)
        return {bank[i].id} if 0 <= i < len(bank) else set()
    # otherwise treat it as a literal question id
    return {q.id for q in bank if q.id == spec}


# -- display helpers --------------------------------------------------------

def _trunc(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def print_question(i: int, q: Question, selected: set[str]):
    mark = "x" if q.id in selected else " "
    meta = f"{q.category or '-'}/{q.difficulty or '-'}"
    print(f"  [{mark}] {i:>3}  {q.id:<16} {_trunc(meta, 28):<28} "
          f"{_trunc(q.question, 50)}")


def list_questions(bank, selected, filt=None):
    rows = 0
    for i, q in enumerate(bank):
        if filt == "sel" and q.id not in selected:
            continue
        if filt == "unsel" and q.id in selected:
            continue
        if filt not in (None, "sel", "unsel") and filt.lower() not in q.category.lower():
            continue
        print_question(i, q, selected)
        rows += 1
    if not rows:
        print("  (no matching questions)")


def print_categories(bank, selected):
    counts: dict[str, list[int]] = {}
    for q in bank:
        cat = q.category or "(uncategorised)"
        tally = counts.setdefault(cat, [0, 0])
        tally[0] += 1
        if q.id in selected:
            tally[1] += 1
    print(f"  {'category':<40} {'sel':>5} / {'total':>5}")
    for cat in sorted(counts):
        total, sel = counts[cat][0], counts[cat][1]
        print(f"  {_trunc(cat, 40):<40} {sel:>5} / {total:>5}")


HELP = """commands:
  cats                  list categories with selected/total counts
  list [filter]         list questions; filter = category substring | sel | unsel
  add <spec>            add questions to the selection
  rm <spec>             remove questions from the selection
  toggle <spec>         flip selection for the matched questions
  clear                 deselect everything
  step [filter]         walk questions one by one, y/n/s/q to include each
  count                 show how many questions are selected
  name <name>           set the whitelist name
  desc <text>           set the whitelist description
  save [name]           write the whitelist to assets/trivia/whitelists/
  help                  show this help
  quit                  exit (prompts if there are unsaved changes)

<spec>: all | <index> | <lo>-<hi> | <question-id> | cat:<substr> | diff:<level>"""


# -- REPL -------------------------------------------------------------------

def run(bank, name, description, selected):
    dirty = False
    print(f"loaded {len(bank)} bank questions. Type 'help' for commands.\n")
    while True:
        try:
            raw = input(f"whitelist[{name or 'unnamed'}:{len(selected)}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raw = "quit"
        if not raw:
            continue
        cmd, _, arg = raw.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()

        if cmd in ("quit", "exit", "q"):
            if dirty and input("unsaved changes; quit anyway? [y/N] ").lower() != "y":
                continue
            return
        elif cmd in ("help", "?"):
            print(HELP)
        elif cmd == "cats":
            print_categories(bank, selected)
        elif cmd == "list":
            list_questions(bank, selected, arg or None)
        elif cmd == "count":
            print(f"  {len(selected)} selected")
        elif cmd in ("add", "rm", "toggle"):
            ids = resolve_spec(arg, bank)
            if not ids:
                print("  spec matched 0 questions")
                continue
            if cmd == "add":
                selected |= ids
            elif cmd == "rm":
                selected -= ids
            else:
                selected ^= ids
            dirty = True
            print(f"  {cmd}: {len(ids)} matched; {len(selected)} now selected")
        elif cmd == "clear":
            selected.clear()
            dirty = True
            print("  cleared")
        elif cmd == "step":
            dirty = step(bank, selected, arg or None) or dirty
        elif cmd == "name":
            name = arg
            print(f"  name = {name!r}")
        elif cmd == "desc":
            description = arg
            print(f"  description = {description!r}")
        elif cmd == "save":
            target = arg or name
            if not target:
                print("  set a name first ('name <name>') or pass one: save <name>")
                continue
            if not selected:
                print("  nothing selected; nothing to save")
                continue
            name = target
            # preserve bank order so diffs stay stable across edits
            ordered = [q.id for q in bank if q.id in selected]
            path = save_whitelist(name, description, ordered)
            dirty = False
            print(f"  saved {len(ordered)} ids -> {os.path.relpath(path, REPO_ROOT)}")
            print(f"  set config.Trivia.WHITELIST = {name!r} to use it")
        else:
            print(f"  unknown command {cmd!r}; type 'help'")


def step(bank, selected, filt):
    """Walk the (optionally filtered) bank, toggling inclusion one at a time."""
    changed = False
    for i, q in enumerate(bank):
        if filt == "sel" and q.id not in selected:
            continue
        if filt == "unsel" and q.id in selected:
            continue
        if filt not in (None, "sel", "unsel") and filt.lower() not in q.category.lower():
            continue
        print(f"\n[{i}] {q.id}  ({q.category or '-'}/{q.difficulty or '-'})  "
              f"currently {'IN' if q.id in selected else 'out'}")
        print(f"    {q.question}")
        for j, choice in enumerate(q.choices):
            star = "*" if j == q.correct_index else " "
            print(f"      {star} {chr(ord('A') + j)}. {choice}")
        ans = input("    include? [y/n/s(kip)/q(uit)] ").strip().lower()
        if ans in ("q", "quit"):
            break
        if ans in ("y", "yes"):
            if q.id not in selected:
                selected.add(q.id)
                changed = True
        elif ans in ("n", "no"):
            if q.id in selected:
                selected.discard(q.id)
                changed = True
        # anything else (incl. 's') leaves it unchanged
    return changed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--edit", metavar="NAME",
                   help="load an existing whitelist by name and edit it")
    args = p.parse_args(argv)

    bank = load_bank()
    name, description, selected = "", "", set()
    if args.edit:
        name = args.edit
        description, selected = load_whitelist(name)
        # drop ids no longer present in the bank so a save can't keep stale entries
        bank_ids = {q.id for q in bank}
        selected = {i for i in selected if i in bank_ids}
    run(bank, name, description, selected)


if __name__ == "__main__":
    main()
