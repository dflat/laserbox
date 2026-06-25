#!/usr/bin/env python3
"""Fetch trivia questions and bake their voice-over (dev/desktop tool).

This is the *sync-time* half of Trivia: it runs on a desktop with internet,
``edge-tts`` and ``ffmpeg`` installed, and turns Open Trivia DB questions into
the local bank + pre-rendered audio the box plays back offline. It never runs on
the Pi.

Three jobs, mix and match:

* ``--fetch N``    pull N multiple-choice questions from OpenTDB and **append**
                   (by id, no duplicates) to ``assets/trivia/bank.json``.
* ``--bake``       render question + 4 choice clips for every bank question that
                   doesn't already have them.
* ``--static``     render the fixed lines, question ordinals, number clips, and
                   the GameSelect ``menu/trivia.wav`` announcement.

All audio is edge-tts with the project voice, converted to the house format
(22050 Hz / mono / 16-bit) to match the rest of ``assets/sounds``. Existing wavs
are skipped unless ``--force``. The tool ``git add``s new files (LFS picks up the
wavs) but never commits or pushes -- that's left to you.

Examples::

    python tools/trivia_sync.py --static                 # one-time fixed VO
    python tools/trivia_sync.py --bake                   # voice the current bank
    python tools/trivia_sync.py --fetch 40 --bake        # grow the bank + voice it
    python tools/trivia_sync.py --fetch 20 --difficulty medium --category 18
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.config import config
from src.programs.trivia_source import Question  # noqa: E402

VOICE = "en-AU-WilliamMultilingualNeural"        # project voice (Australian male)
SAMPLE_RATE, CHANNELS = 22050, 1                 # house audio format
BANK_PATH = os.path.join(REPO_ROOT, config.Trivia.BANK_PATH)
EFFECTS_ROOT = os.path.join(REPO_ROOT, "assets", "sounds", "effects")
TRIVIA_DIR = os.path.join(EFFECTS_ROOT, "trivia")

# Fixed lines whose text never depends on a question. Keys are paths under the
# trivia effects dir; they mirror PrebakedVoice.STATIC.
STATIC_TEXT = {
    "vo/both_teams_buzz_to_begin.wav": "Both teams, buzz in to begin.",
    "vo/both_ready_lets_begin.wav": "Both teams are ready. Let's begin!",
    "vo/no_one_buzzed.wav": "Nobody buzzed in.",
    "vo/five_seconds_remaining.wav": "Five seconds remaining.",
    "vo/the_correct_answer_is.wav": "The correct answer is:",
    "vo/black_team_steal.wav": "Black team, here is your chance to steal.",
    "vo/white_team_steal.wav": "White team, here is your chance to steal.",
    "vo/black_team_wins.wav": "Black team wins!",
    "vo/white_team_wins.wav": "White team wins!",
    "vo/its_a_tie.wav": "It's a tie!",
    "vo/sudden_death.wav": "Sudden death!",
    "vo/black_team.wav": "Black team:",
    "vo/white_team.wav": "White team:",
    # spoken choice labels read before each option during the question read-out
    "vo/choice_label_a.wav": "A:",
    "vo/choice_label_b.wav": "B:",
    "vo/choice_label_c.wav": "C:",
    "vo/choice_label_d.wav": "D:",
}

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_ORDINALS = ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth",
             "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth",
             "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
             "eighteenth", "nineteenth", "twentieth"]


def number_words(n: int) -> str:
    """Spell a non-negative integer (0..99) in words for TTS."""
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


# -- tool checks ------------------------------------------------------------

def _require_tools():
    import shutil
    missing = [t for t in ("edge-tts", "ffmpeg") if shutil.which(t) is None]
    if missing:
        sys.exit(f"error: missing required tool(s): {', '.join(missing)}. "
                 "Install edge-tts (pip) and ffmpeg, then retry.")


def synth(text: str, out_rel: str, force: bool) -> bool:
    """Render ``text`` to ``EFFECTS/trivia/<out_rel>`` in the house format.

    Returns True if a file was (re)written, False if skipped (already present).
    """
    out_path = os.path.join(TRIVIA_DIR, out_rel)
    if os.path.exists(out_path) and not force:
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "clip.mp3")
        subprocess.run(["edge-tts", "--voice", VOICE, "--text", text,
                        "--write-media", mp3], check=True)
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(SAMPLE_RATE),
                        "-ac", str(CHANNELS), "-sample_fmt", "s16", out_path],
                       check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    print(f"  baked {out_rel}")
    return True


# -- bank IO ----------------------------------------------------------------

def load_bank() -> list:
    if not os.path.exists(BANK_PATH):
        return []
    with open(BANK_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["questions"] if isinstance(data, dict) else data


def save_bank(records: list, extra: dict | None = None):
    payload = {"questions": records}
    if extra:
        payload.update(extra)
    with open(BANK_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# -- jobs -------------------------------------------------------------------

def do_fetch(amount: int, difficulty: str, category):
    import requests
    params = {"amount": min(amount, 50), "type": "multiple"}
    if difficulty in ("easy", "medium", "hard"):
        params["difficulty"] = difficulty
    if category:
        params["category"] = category
    print(f"fetching {params['amount']} questions from OpenTDB ...")
    resp = requests.get("https://opentdb.com/api.php", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("response_code") != 0 or not data.get("results"):
        sys.exit(f"OpenTDB returned response_code={data.get('response_code')}")

    existing = load_bank()
    # append-only by id so curated playlists referencing positional indices stay
    # valid across syncs
    keep = {r["id"] for r in existing}
    merged = list(existing)
    added = 0
    for entry in data["results"]:
        q = Question.from_opentdb(entry)
        if q.id in keep:
            continue
        merged.append(q.to_dict())
        keep.add(q.id)
        added += 1
    # preserve the human-readable _note that lives outside the questions list
    extra = {}
    if os.path.exists(BANK_PATH):
        with open(BANK_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and "_note" in doc:
            extra["_note"] = doc["_note"]
    save_bank(merged, extra)
    print(f"added {added} new question(s); bank now has {len(merged)}")


def do_bake(force: bool):
    records = load_bank()
    if not records:
        sys.exit("bank is empty; run --fetch first (or author bank.json)")
    print(f"baking audio for {len(records)} bank question(s) ...")
    wrote = 0
    for rec in records:
        q = Question.from_dict(rec)
        wrote += synth(q.question, f"q/{q.id}/question.wav", force)
        for i, choice in enumerate(q.choices):
            wrote += synth(choice, f"q/{q.id}/choice{i}.wav", force)
    print(f"bake complete: {wrote} clip(s) written")


def do_static(max_questions: int, max_score: int, force: bool):
    print("baking static voice-over ...")
    wrote = 0
    for rel, text in STATIC_TEXT.items():
        wrote += synth(text, rel, force)
    # question ordinals: "First question:" .. plus the sudden-death intro. The
    # ordinal leads (read as "first question", not "question first").
    for n in range(1, max_questions + 1):
        ordinal = _ORDINALS[n] if n < len(_ORDINALS) else f"{number_words(n)}th"
        wrote += synth(f"{ordinal.capitalize()} question:", f"vo/question_{n}.wav", force)
    wrote += synth("Sudden death! Question:", "vo/question_sudden.wav", force)
    # number clips for score read-out (0..max_score, plus "minus")
    for n in range(0, max_score + 1):
        wrote += synth(number_words(n), f"num/{n}.wav", force)
    wrote += synth("negative", "num/minus.wav", force)
    # GameSelect menu announcement lives under effects/menu, not trivia/
    menu_wav = os.path.join(EFFECTS_ROOT, "menu", "trivia.wav")
    if force or not os.path.exists(menu_wav):
        os.makedirs(os.path.dirname(menu_wav), exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = os.path.join(tmp, "m.mp3")
            subprocess.run(["edge-tts", "--voice", VOICE, "--text", "Trivia.",
                            "--write-media", mp3], check=True)
            subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(SAMPLE_RATE),
                            "-ac", str(CHANNELS), "-sample_fmt", "s16", menu_wav],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        print("  baked menu/trivia.wav")
        wrote += 1
    print(f"static bake complete: {wrote} clip(s) written")


def git_add():
    """Stage new/changed assets (LFS handles the wavs). No commit/push."""
    try:
        subprocess.run(["git", "-C", REPO_ROOT, "add",
                        "assets/trivia", "assets/sounds/effects/trivia",
                        "assets/sounds/effects/menu/trivia.wav"], check=False)
        print("staged trivia assets (review and commit yourself)")
    except Exception as e:
        print(f"git add skipped: {e}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fetch", type=int, metavar="N",
                   help="fetch N multiple-choice questions and append to the bank")
    p.add_argument("--difficulty", default=config.Trivia.DIFFICULTY,
                   choices=["any", "easy", "medium", "hard"])
    p.add_argument("--category", type=int, default=None,
                   help="OpenTDB category id (optional)")
    p.add_argument("--bake", action="store_true",
                   help="render question + choice clips for the whole bank")
    p.add_argument("--static", action="store_true",
                   help="render fixed lines, ordinals, numbers, menu clip")
    p.add_argument("--force", action="store_true",
                   help="re-render clips even if the wav already exists")
    p.add_argument("--max-questions", type=int, default=12,
                   help="highest 'Question N' ordinal to bake (default 12)")
    p.add_argument("--max-score", type=int, default=None,
                   help="highest score number to bake (default 2*QUESTIONS_PER_MATCH)")
    args = p.parse_args(argv)

    if not (args.fetch or args.bake or args.static):
        p.error("nothing to do: pass --fetch, --bake, and/or --static")

    if args.bake or args.static:
        _require_tools()

    if args.fetch:
        do_fetch(args.fetch, args.difficulty, args.category)
    if args.static:
        max_score = (args.max_score if args.max_score is not None
                     else 2 * config.Trivia.QUESTIONS_PER_MATCH)
        do_static(args.max_questions, max_score, args.force)
    if args.bake:
        do_bake(args.force)

    git_add()


if __name__ == "__main__":
    main()
