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
- First-time setup: `python3.12 -m venv .venv && source .venv/bin/activate
  && pip install -e ".[dev]"`.
- Activate venv: `source .venv/bin/activate` (or use `.venv/bin/python`).
- Run TUI: `python -m spqr` (or `--seed N`, `--load PATH`).
- Headless: `python -m spqr --headless --seed 42 --ticks 5000`.
- State hash for determinism check: `... --hash-only`.
- Tests: `pytest` (single test: `pytest tests/test_grain.py::test_name`).

## Invariants — do not break
- **All mutable state lives on `GameState`** (`engine/world.py`). Off-tree
  state (live `random.Random`) is reconstructed at load via `RngState`.
- **Deterministic**: every system takes `(state, rng)` and uses only that
  RNG. No module-level `random`, no clock reads, no I/O in the tick path.
  Same seed + same command sequence ⇒ identical state hash.
- **One tick = one in-game hour.** Time constants in `engine/world.py`
  (`HOURS_PER_DAY`, `HOURS_PER_MONTH`, `HOURS_PER_YEAR`).
- **System order matters** (`sim/systems/__init__.py`): labor →
  construction → grain → industry → housing → economy → population.
  Labor must run first so `workers_assigned` is set before any consumer
  reads it; `grain` runs the full food pipeline (farm growth,
  cart-to-granary, scheduled meals, treasury aggregate sync) and must
  precede `economy`, which drains granaries for the dole. `industry`
  (lumber mills + quarries pumping timber/stone into the treasury,
  capped by total storage) sits before `housing` so the month's tier
  upgrades see the just-produced materials. `housing` (monthly
  residence tier upgrades) sits before `population` so the same
  month's migration sees the bumped capacity. Adding a new system:
  think about which side of `economy` it belongs.
- **Granary reach is a Dijkstra cost-12 walk** computed in
  `sim/systems/spatial.py::coverage`. The same primitive backs both the
  grain pipeline and the `i` info-screen range highlight — never
  reimplement it in the UI, or the highlight will silently drift from
  what the simulation uses.
- **Housing capacity is tier-aware** via
  `sim/models/building.py::residence_capacity`. Every consumer (grain
  meal demand, migration cap, inspector display) routes through this
  helper. RESIDENCE is the building kind; tier 0/1/2/3 carry the
  actual class ("undeveloped"/"huts"/"cottages"/"insula") via
  `RESIDENCE_TIER_NAME`. Tier 1 needs only timber; tier 2+ needs
  timber AND stone (`RESIDENCE_TIER_UPGRADE_TIMBER_COST` /
  `_STONE_COST`). Reading `RESIDENCE_TIER_CAPACITY[…]` directly
  bypasses the kind check and desyncs systems — same shape of bug as
  reimplementing `coverage`.
- **Farm output is crop-driven** via `farm_worker_slots()`,
  `farm_worker_hours_per_harvest()`, and `farm_yield_per_harvest()` in
  `sim/models/building.py`. WHEAT (1 worker, monthly cycle, 150 grain)
  ships to granaries; VEGETABLES (4 workers, ~5-day cycle, 80 yield)
  ships to warehouses. Labor and grain both route through these helpers
  so a wheat farm correctly draws 1 worker.
- **Two food pipelines, mirrored.** Grain: wheat farms →
  `grain_stored` → granaries → `treasury.grain`. Vegetables: veg farms
  → `vegetables_stored` → warehouses → `treasury.vegetables`. Both use
  the same `spatial.coverage` reach. Pleb meals draw from both when
  both are in reach (50/50 split, with shortfall topping up from the
  other side). Patrician meals stay grain-only. Each meal that meets
  demand from N distinct food types adds `0.003 × N` to district
  satisfaction — the food-variety desirability bonus.
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
