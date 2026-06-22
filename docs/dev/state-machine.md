# State machine, contexts & program lifecycle

Everything in this page lives in {mod}`src.programs.base`.

## State and StateSequence

{class}`src.programs.base.State` wraps the 16-bit input word:

- low 14 bits → **buttons** (`state.buttons`, `state.get_buttons_on()`)
- top 2 bits → **toggles** (`state.toggles` is 0–3, `state.get_toggles_on()`)

It supports the bitwise operators and equality against a raw int, so diffing two
states is just `a ^ b`. Build one from indices with
`State.from_list(buttons=[0,1], toggles=(1,0))`.

{class}`src.programs.base.StateSequence` is an ordered list of states with a
fuzzy, in-order `match()`: with a `maxlen` larger than the pattern, the target
states must appear *in order* but need not be adjacent. (Used by the
trigger-matching helpers; most games don't need it directly.)

## The state machine

{class}`src.programs.base.StateMachine` owns exactly one **active program** at a
time and routes control between programs. Two class-level registries drive it:

- `PROGRAMS` — class name → `Program` singleton. A program registers itself
  simply by being instantiated once (see {doc}`authoring-programs`).
- `COMPOSER_CLASSES` — class name → `Composer` subclass, populated by the
  `@StateMachine.register_composer` decorator.

Each frame, {meth}`~src.programs.base.StateMachine.update` does two things:

1. **Global entry gesture.** Unless GameSelect is already active, it feeds the
   latest input state to the {class}`~src.programs.base.GestureDetector`. If the
   gesture completes, it tears down the running program and enters GameSelect.
2. **Tick the active program** via `program.update(dt)`.

## Contexts (composers)

A **context** is the unit of "what to run". It is a
{class}`src.programs.base.Composer`: an ordered script of program names (plus
per-program start kwargs). The state machine holds the current context in
`self.context`.

- A single game is wrapped in a {class}`~src.programs.base.SingleEntryComposer`
  (a one-item context).
- A multi-game show is a `Composer` subclass, e.g.
  {class}`~src.programs.base.BirthdayComposer`.

When a program finishes it calls `quit()`, which calls
{meth}`~src.programs.base.StateMachine.swap_program`. That advances the context
to its next program; **when the context is exhausted, control returns to
GameSelect**. This is what makes "run one game" and "run a whole show" behave
uniformly — both just run a context and come home.

```
GameSelect ──launch_context(target)──▶ context ──next──▶ program ──next──▶ … 
     ▲                                                                      │
     └──────────────────── context exhausted (or entry gesture) ───────────┘
```

### Key state-machine methods

| Method | What it does |
|--------|--------------|
| `enter_game_select()` | Tear down current program, clear the context, activate GameSelect. The box boots via this. |
| `launch_context(target)` | Resolve `target` to a one-item context (a Program name) or a registered Composer, then start it. Called by GameSelect. |
| `swap_program()` | Advance the current context; return to GameSelect when it ends. Called by `Program.quit()`. |
| `_activate_program(name, **kw)` | The single choke-point that **tears down** the old program and **starts** the new one cleanly. |

## Teardown: why switching is safe

Switching programs (for any reason — finish, advance, or mid-game interrupt)
goes through `_activate_program`, which performs a **hard teardown** of the
outgoing program before starting the next:

1. `program.teardown()` — drop the program's pending `after()` callbacks and
   cooldowns.
2. `mixer.stop_all()` — stop music and every playing effect.
3. `Animation.kill_all()` — stop all running animations.
4. `lasers.set_word(0)` — clear the field.
5. `events.clear()` — drop stale input events so they don't leak forward.
6. `gesture.reset()` — so still-held trigger buttons can't immediately re-fire.

```{important}
`scheduler` and `cooldowns` are **per-instance** (created in `Program.__init__`),
not shared class state. This matters because the box can interrupt a game at any
moment; a leaked callback from one game must never fire inside another.
```

## The Program lifecycle

```
register (at import)         make_active_program(game)        per frame
  Program()  ─────────────▶   binds self.game,         ─────▶  update(dt)
  (singleton in PROGRAMS)      self.input_manager                 │
                                     │                            │ quit()
                                     ▼                            ▼
                                  start(**kwargs)            swap_program()
                                  (setup audio/lasers)       → teardown → next
```

- **`__init__`** runs once at import; call `super().__init__()`. Do *static*
  setup only (no `self.game` yet).
- **`start(**kwargs)`** runs each time the program is activated. Load audio,
  set up lasers, init round state. `kwargs` come from the context's
  `program_kwargs`.
- **`update(dt)`** runs every frame; call `super().update(dt)` so cooldown and
  scheduler bookkeeping run. Drain `events` here.
- **`quit()`** ends the program and advances the context. Override to add
  cleanup, then call `super().quit()`.
- **`teardown()`** is called *by the state machine* on switch-away; override only
  for unusual resources, and call `super().teardown()`.

## The GameSelect entry gesture

GameSelect is reachable from **any** running program via a global gesture,
detected by {class}`~src.programs.base.GestureDetector` at the state-machine
level (not inside each program). It is *non-consuming* — it reads input state
rather than pulling from the event queue — so it is immune to how a game handles
its own input, and it is *masked*: only the configured hold-buttons and toggle
matter.

Defaults ({class}`config.GameSelect <src.config.config.GameSelect>`): hold
buttons **0 & 1** while toggle **0** changes state **twice** (e.g. on→off→on).
All hold buttons must remain pressed across both transitions; releasing any one
resets the detector. The gesture is ignored while GameSelect is already active.

See {doc}`authoring-programs` to build a game that plugs into all of this.
