# SPQR — Roman City Simulation Engine

Text/terminal city sim, Dwarf Fortress × SimCity, ancient-Roman themed.
The MVP is "engine first": deterministic tick loop, procgen world,
hybrid agent/aggregate population, Textual TUI.

**Read `@JOURNAL.md` first** — it tracks decisions, what worked, what
broke, and known gotchas. Append a new dated entry at the top after any
substantive change.

## Stack
- Python 3.12+, `textual` (TUI), `msgspec` (state + msgpack save/load),
  `numpy` (procgen + aggregate math), `pytest`.
- Project layout: `src/spqr/{engine,sim/{models,systems},world/procgen,
  ui,persistence}`; tests in `tests/`.

## Commands
- Activate venv: `source .venv/bin/activate` (or use `.venv/bin/python`).
- Run TUI: `python -m spqr` (or `--seed N`, `--load PATH`).
- Headless: `python -m spqr --headless --seed 42 --ticks 5000`.
- State hash for determinism check: `... --hash-only`.
- Tests: `pytest`.

## Invariants — do not break
- **All mutable state lives on `GameState`** (`engine/world.py`). Off-tree
  state (live `random.Random`) is reconstructed at load via `RngState`.
- **Deterministic**: every system takes `(state, rng)` and uses only that
  RNG. No module-level `random`, no clock reads, no I/O in the tick path.
  Same seed + same command sequence ⇒ identical state hash.
- **One tick = one in-game hour.** Time constants in `engine/world.py`
  (`HOURS_PER_DAY`, `HOURS_PER_MONTH`, `HOURS_PER_YEAR`).
- **System order matters** (`sim/systems/__init__.py`): construction →
  labor → economy → population → military → agents → events.
  Adding a new system: think about which side of `economy` it belongs.
- **`msgspec.Struct` typed fields**: construct with the declared type.
  An `int` passed to a `float` field will silently round-trip-coerce and
  break encode-byte-stability (see JOURNAL 2026-04-25).
- **Schema versioning**: bump `persistence/schema.py::SCHEMA_VERSION`
  whenever `GameState` shape changes incompatibly. No migration path
  in MVP — old saves should fail loudly.
- **`Engine.apply_pending()` runs every UI frame**, not only inside
  `step()`. Required so commands (pause/resume/etc.) drain even when
  the sim is paused.

## Map / world
- Region: 32×32 tiles, ~5 km each. `world/procgen/region.py`.
- City: 60×30 tiles, ~30 m each. `world/procgen/city.py`.
- Both sizes are module constants; not configurable in MVP.

## Verification gates before calling something done
- `pytest` green.
- `python -m spqr --headless --seed 42 --ticks 1000 --hash-only` is
  stable across runs.
- For TUI changes: `app.run_test()` pilot test with `pilot.press(...)`
  and assertions on `engine.state` (see how the smoke checks were
  written in the JOURNAL session).

## Out of MVP scope (don't pull in unprompted)
Senate/cursus honorum, faction politics, market simulation, religion
beyond stubs, naval/siege warfare, multi-province empires, modding API,
z-levels. Each would shift architecture; surface them as proposals
before starting.
