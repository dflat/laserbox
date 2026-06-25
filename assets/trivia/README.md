# Trivia — content & game management

Everything you need to **author questions, bake their voice-over, and curate a
particular match** for the Trivia mini-game (`src/programs/trivia.py`). This is the
operator's guide to the *content*, not the gameplay code — for how a round plays
out (buzz-in, steal, scoring) read the docstring at the top of `trivia.py`.

All commands are run **from the repo root** with the project virtualenv
(`.venv/bin/python`), e.g. `.venv/bin/python tools/trivia_sync.py --bake`.

- [The pieces](#the-pieces)
- [Three ways to shape a match](#three-ways-to-shape-a-match)
- [Tool 1 — `trivia_sync.py` (bank + audio)](#tool-1--trivia_syncpy-bank--audio)
- [Tool 2 — `trivia_whitelist.py` (bank subsets)](#tool-2--trivia_whitelistpy-bank-subsets)
- [Categories & difficulties (and their integer ids)](#categories--difficulties-and-their-integer-ids)
- [Authoring questions by hand](#authoring-questions-by-hand)
- [`config.Trivia` reference](#configtrivia-reference)
- [End-to-end recipes](#end-to-end-recipes)
- [Deploying to the box](#deploying-to-the-box)

---

## The pieces

| Thing | Where | What it is |
|---|---|---|
| **Question bank** | `assets/trivia/bank.json` | The full pool of questions. **Append-only, stable order** so positional indices stay valid. |
| **Voice-over** | `assets/sounds/effects/trivia/` | Pre-baked `.wav` clips (Git LFS). `q/<id>/question.wav`, `q/<id>/choice{0..3}.wav`, plus fixed lines/numbers under `vo/` and `num/`. |
| **Whitelists** | `assets/trivia/whitelists/<name>.json` | Named **subsets** of the bank to draw from (see below). |
| **Menu clip** | `assets/sounds/effects/menu/trivia.wav` | The "Trivia." announcement on the home menu (slot 6). |

The box runs **fully offline**: it plays from the local bank with pre-baked audio
(the Pi Zero W can't synthesise speech). Fetching questions and baking audio is a
**desktop-only, sync-time** job. The audio `.wav`s are large and live in Git LFS —
see the root `README.md` for the LFS mental model.

A question record looks like this (note the **frozen choice order** — the audio for
each slot is baked in this order, so never reorder `choices` without re-baking):

```json
{
  "id": "geo-aus-capital",
  "category": "Geography",
  "difficulty": "easy",
  "question": "What is the capital city of Australia?",
  "choices": ["Sydney", "Canberra", "Melbourne", "Perth"],
  "correct_index": 1
}
```

`id` doubles as the audio-folder name (`assets/sounds/effects/trivia/q/geo-aus-capital/`).

---

## Three ways to shape a match

The game draws its questions one of three ways, controlled by `config.Trivia`
(`src/config.py`). **Curation precedence: `CURATED_PLAYLIST` > `WHITELIST` > whole bank.**

| Mode | Set in config | Behaviour |
|---|---|---|
| **Random (default)** | `WHITELIST = None`, `CURATED_PLAYLIST = None` | Shuffle the whole bank, play `QUESTIONS_PER_MATCH` distinct questions. |
| **Whitelist** | `WHITELIST = "name"` | Same random draw, but **only from the whitelisted subset** of the bank. Still `QUESTIONS_PER_MATCH` questions, still random each match. Build one with `trivia_whitelist.py`. |
| **Curated playlist** | `CURATED_PLAYLIST = [...]` | Play an **exact, ordered, predetermined** list of questions. Match length becomes the length of the list. |

The key distinction the platform makes:

- A **whitelist** narrows *which questions are eligible*; the match is still a
  random sample of N from that pool, and replays differently every time.
- A **curated playlist** *is* the match: a fixed N questions in a fixed order,
  identical every play. Use it for a scripted/demo run; use a whitelist for "only
  ask science & geography, but keep it fresh."

> `DIFFICULTY` and `CATEGORY` in `config.Trivia` only affect the **live OpenTDB**
> source (which the box never uses). To restrict difficulty/category for the
> offline box, build a **whitelist** (`diff:` / `cat:` filters) instead.

---

## Tool 1 — `trivia_sync.py` (bank + audio)

`tools/trivia_sync.py` grows the bank and renders its voice-over. It runs on a
desktop with internet (for `--fetch`), and `edge-tts` + `ffmpeg` on PATH (for any
baking). **It never runs on the Pi.** All audio is rendered with the project voice
`en-AU-WilliamMultilingualNeural` and converted to the house format (22050 Hz,
mono, 16-bit PCM). Existing clips are skipped unless `--force`. It `git add`s new
assets at the end (LFS picks up the wavs) but **never commits or pushes**.

### Flags

| Flag | Default | Does |
|---|---|---|
| `--fetch N` | — | Pull `N` multiple-choice questions from OpenTDB and **append by id** (no dupes) to the bank. |
| `--difficulty {any,easy,medium,hard}` | `config.Trivia.DIFFICULTY` | Difficulty filter for `--fetch`. |
| `--category INT` | none | OpenTDB **category id** for `--fetch` (see [the table below](#categories--difficulties-and-their-integer-ids)). |
| `--bake` | — | Render `question.wav` + 4 `choice{i}.wav` for every bank question that lacks them. |
| `--static` | — | Render the fixed lines (prompts, steal/win lines, **`A:`–`D:` choice labels**), question ordinals, score numbers, and the menu clip. |
| `--force` | off | Re-render even if the wav already exists. |
| `--max-questions N` | `12` | Highest "Nth question:" ordinal to bake under `--static`. **Raise this if you raise `QUESTIONS_PER_MATCH` above 12.** |
| `--max-score N` | `2 × QUESTIONS_PER_MATCH` | Highest score number to voice (a "negative" clip covers minus). |

You must pass at least one of `--fetch`, `--bake`, `--static`. Jobs combine, e.g.
`--fetch 40 --bake` grows the bank then voices the new questions.

### Typical use

```bash
# One-time: bake the fixed lines, ordinals, numbers, choice labels, menu clip
.venv/bin/python tools/trivia_sync.py --static

# Grow the bank with 20 medium Science: Computers questions, then voice them
.venv/bin/python tools/trivia_sync.py --fetch 20 --difficulty medium --category 18 --bake

# You hand-edited bank.json — just voice whatever is missing
.venv/bin/python tools/trivia_sync.py --bake

# Re-render a question whose text you changed (force overwrites)
.venv/bin/python tools/trivia_sync.py --bake --force
```

> **After any change to the read-out clips, run `--static` once.** The first-read
> question now speaks each option behind a spoken letter ("A: …, B: …"), which uses
> the `vo/choice_label_{a..d}.wav` clips that `--static` bakes.

---

## Tool 2 — `trivia_whitelist.py` (bank subsets)

`tools/trivia_whitelist.py` interactively builds a **whitelist** — a named subset
of the bank to draw from. It only reads the bank and writes a small JSON file, so
it needs no audio tools or network. Whitelists are saved to
`assets/trivia/whitelists/<name>.json` as `{"name", "description", "ids"}`.

```bash
.venv/bin/python tools/trivia_whitelist.py            # start a new whitelist
.venv/bin/python tools/trivia_whitelist.py --edit sci # load + edit an existing one
```

It drops you into a small REPL. The prompt shows the current name and selection
count: `whitelist[sci:12]>`.

### Commands

| Command | Does |
|---|---|
| `cats` | List every category in the bank with `selected / total` counts. |
| `list [filter]` | List questions. `filter` = a **category substring**, or `sel` / `unsel`. |
| `add <spec>` | Add the matched questions to the selection. |
| `rm <spec>` | Remove the matched questions. |
| `toggle <spec>` | Flip selection for the matched questions. |
| `clear` | Deselect everything. |
| `step [filter]` | Walk questions one at a time; answer `y`/`n`/`s`(kip)/`q`(uit) to include each. Shows the choices with the correct one starred. |
| `count` | Print how many questions are selected. |
| `name <name>` | Set the whitelist's name (the filename). |
| `desc <text>` | Set its description. |
| `save [name]` | Write it out (ids stored in bank order for stable diffs). |
| `help` | Show the command list. |
| `quit` | Exit (prompts if there are unsaved changes). |

### `<spec>` — the selection grammar

`add` / `rm` / `toggle` all take a spec:

| Spec | Matches |
|---|---|
| `all` | Every question in the bank. |
| `5` | The question at **bank index 5**. |
| `5-9` | Bank indices 5 through 9 inclusive. |
| `geo-aus-capital` | A question by its literal **id**. |
| `cat:geography` | Every question whose **category string contains** "geography" (case-insensitive). |
| `diff:easy` | Every question with difficulty exactly `easy` (`easy`/`medium`/`hard`). |

### Example session

```
$ .venv/bin/python tools/trivia_whitelist.py
whitelist[unnamed:0]> cats                 # see what's in the bank
whitelist[unnamed:0]> add cat:Science      # all science questions
whitelist[unnamed:0]> add cat:Geography
whitelist[unnamed:0]> rm diff:hard         # drop the hard ones
whitelist[unnamed:0]> list sel             # review the selection
whitelist[unnamed:0]> desc Science + geography, easy/medium only
whitelist[unnamed:0]> save sci-geo
  saved 17 ids -> assets/trivia/whitelists/sci-geo.json
  set config.Trivia.WHITELIST = 'sci-geo' to use it
whitelist[sci-geo:17]> quit
```

Then in `src/config.py`: `WHITELIST = "sci-geo"`.

> `--edit` drops ids that no longer exist in the bank, so re-saving an old
> whitelist won't keep stale entries. **No audio step is needed** — whitelisted
> questions are ordinary bank questions whose audio was already baked.

---

## Categories & difficulties (and their integer ids)

There are **two different "category" mechanisms** — don't mix them up:

1. **`trivia_sync.py --category <INT>`** uses the **OpenTDB numeric category id**.
   It applies only when **fetching** new questions from the internet.
2. **`trivia_whitelist.py`'s `cat:<text>`** matches the **category string already
   stored on bank questions** (a substring, case-insensitive). It's what you use
   to curate the offline bank.

### OpenTDB category ids (for `--fetch --category`)

These ids are stable. The canonical, always-current list is the API itself:

```bash
curl -s https://opentdb.com/api_category.php | python3 -m json.tool
```

At time of writing:

| id | category | id | category |
|---:|---|---:|---|
| 9  | General Knowledge | 22 | Geography |
| 10 | Entertainment: Books | 23 | History |
| 11 | Entertainment: Film | 24 | Politics |
| 12 | Entertainment: Music | 25 | Art |
| 13 | Entertainment: Musicals & Theatres | 26 | Celebrities |
| 14 | Entertainment: Television | 27 | Animals |
| 15 | Entertainment: Video Games | 28 | Vehicles |
| 16 | Entertainment: Board Games | 29 | Entertainment: Comics |
| 17 | Science & Nature | 30 | Science: Gadgets |
| 18 | Science: Computers | 31 | Entertainment: Japanese Anime & Manga |
| 19 | Science: Mathematics | 32 | Entertainment: Cartoon & Animations |
| 20 | Mythology | | |
| 21 | Sports | | |

Difficulty for `--fetch` is one of `any` / `easy` / `medium` / `hard`.

### What's actually in *your* bank

The category **strings** OpenTDB returns (e.g. `"Science: Computers"`) are what get
stored, so a fetched question's category matches the names above. Hand-authored
questions can use any string you like. To see the categories/difficulties present
in the current bank (which is what `cat:` / `diff:` filter against), run `cats`
in the whitelist tool, or:

```bash
.venv/bin/python -c "import json,collections; \
d=json.load(open('assets/trivia/bank.json')); \
c=collections.Counter((q['category'],q['difficulty']) for q in d['questions']); \
[print(f'{n:>3}  {cat} / {diff}') for (cat,diff),n in sorted(c.items())]"
```

---

## Authoring questions by hand

You can edit `assets/trivia/bank.json` directly instead of (or in addition to)
fetching. Rules that keep things consistent:

- The file is `{"questions": [ ... ], "_note": "..."}`. **Append; never reorder or
  delete** — `CURATED_PLAYLIST` may reference positional indices, and reordering
  would silently change which questions a curated match plays.
- Each record needs `id`, `question`, `choices` (exactly **4**), and
  `correct_index` (0–3, pointing into `choices`). `category` / `difficulty` are
  optional but power the whitelist `cat:`/`diff:` filters.
- Pick a **short, stable, human-readable `id`** (e.g. `geo-aus-capital`). It names
  the audio folder, so it must be unique and filesystem-safe. (Fetched questions
  get an 8-hex-char hash id instead.)
- `choices` order is **frozen** — the baked audio (`choice0..3`) lines up with it
  and with the buttons. Editing the order or text means re-baking (`--bake --force`).
- After adding questions, **bake their audio**: `.venv/bin/python
  tools/trivia_sync.py --bake`. Missing clips are tolerated at runtime (skipped to
  silence), so the game still runs before baking — handy for simulator logic checks.

---

## `config.Trivia` reference

The knobs that decide how a match is shaped and sourced (`src/config.py`):

| Setting | Default | Meaning |
|---|---|---|
| `QUESTIONS_PER_MATCH` | `7` | Questions per match (random / whitelist modes). |
| `WHITELIST` | `None` | Whitelist name (no extension) under `WHITELIST_DIR`, or `None` for the whole bank. |
| `CURATED_PLAYLIST` | `None` | Exact ordered list of ids (str) **or** positional indices (int); wins over `WHITELIST`. |
| `DIFFICULTY` / `CATEGORY` | `"any"` / `None` | **Live-fetch only** filters — no effect on the offline box. |
| `FORCE_MODE` | `None` | Pin the `(source, voice)` pair, e.g. `("bank", "prebaked")`. `None` auto-detects (resolves to bank + prebaked on the box). |
| `ANSWER_TIMEOUT_MS` | `15000` | Choice-selection window after a buzz (with a 5-second warning; **not** reset by re-arming). |
| `POST_QUESTION_BUZZ_MS` | `5000` | Buzz-in window after the question + choices finish reading (no warning). |
| `WARNING_MS` | `5000` | "Five seconds remaining" lead time before the answer deadline. |
| `BANK_PATH` | `assets/trivia/bank.json` | The bank. |
| `WHITELIST_DIR` | `assets/trivia/whitelists` | Where whitelists live. |
| `EFFECT_DIR` | `trivia` | Voice-over root under `assets/sounds/effects`. |

### Curated playlist examples

```python
# Exactly these five, in this order, every match:
CURATED_PLAYLIST = ["geo-aus-capital", "sci-red-planet", "hist-moon-landing",
                    "math-hexagon-sides", "lit-romeo-juliet"]

# By positional index into bank.json (0-based):
CURATED_PLAYLIST = [0, 1, 6, 3, 4]
```

Leftover bank questions (shuffled) back any sudden-death tie-breakers.

---

## End-to-end recipes

**Spin up a brand-new bank from scratch**
```bash
.venv/bin/python tools/trivia_sync.py --fetch 50 --bake   # fetch + voice
.venv/bin/python tools/trivia_sync.py --static            # fixed lines/labels/menu
# review bank.json, then commit (see below)
```

**A "kids' science night" themed game (fresh each play)**
```bash
.venv/bin/python tools/trivia_sync.py --fetch 30 --difficulty easy --category 17 --bake
.venv/bin/python tools/trivia_whitelist.py     # add cat:Science, rm diff:hard, save kids-sci
# config.Trivia.WHITELIST = "kids-sci"
```

**A fixed demo reel (identical every time)**
```python
# config.Trivia
CURATED_PLAYLIST = ["geo-aus-capital", "sci-red-planet", "hist-moon-landing"]
```

**Preview any of it offline** (simulator, keyboard-driven):
```bash
.venv/bin/python -m src -s -p Trivia
```

---

## Deploying to the box

New questions/whitelists/audio reach the box like any other change:

1. **Commit** — `git add` the JSON (and the `.wav`s, which LFS handles) and commit.
   The desktop hosting Forgejo LFS must be **on** to push the audio blobs.
2. **On the Pi** — `cd ~/electronics/laserbox && git pull && git lfs pull`, then
   restart the service so it reloads:
   `XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart laserbox`.

See the root `README.md` and `CLAUDE.md` for the full LFS + deploy story.
