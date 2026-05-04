# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
SPQR — a text/terminal Roman city sim (Dwarf Fortress × SimCity), engine-first
MVP. Deterministic tick loop, procgen world, hybrid agent/aggregate population,
Textual TUI.

## Stack
Python 3.12+, `textual` (TUI), `msgspec` (state + msgpack save/load),
`numpy` (procgen + aggregate math), `pytest`. Source under `src/spqr/{engine,
sim/{models,systems},world/procgen,ui,persistence}`; tests under `tests/`.

## Commands
- First-time setup: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Activate venv: `source .venv/bin/activate` (or use `.venv/bin/python`)
- Run TUI: `python -m spqr` (or `--seed N`, `--load PATH`, `--no-splash`)
- Headless: `python -m spqr --headless --seed 42 --ticks 5000`
- Determinism check: `python -m spqr --headless --seed 42 --ticks 5000 --hash-only`
- Tests: `pytest` (single test: `pytest tests/test_grain.py::test_name`)

**Do not run `pytest` or the headless determinism check unless the user asks.**
Write tests; leave running to the user. Same rule for TUI pilot tests
(`app.run_test()` with `pilot.press(...)`).

## Architecture — the tick loop

The whole sim is a fixed pipeline of pure-ish functions over `GameState`:

1. `Engine.step(n)` (engine/tick.py) for each tick: drain pending commands,
   bump `state.tick`, then run each registered system in fixed order.
2. Systems take `(state, rng)` and mutate state in place. **Same seed +
   same command sequence ⇒ identical state hash.** No module-level
   `random`, no clock reads, no I/O in the tick path.
3. `Engine.apply_pending()` is also called every UI frame, not only inside
   `step()` — required so commands (pause/resume/etc.) drain even when
   the sim is paused.

**System order matters** (`sim/systems/__init__.py`):
labor → construction → grain → industry → housing → economy → population.
- labor must run first so `workers_assigned` is set before any consumer reads it
- grain runs the full food pipeline (farm growth, cart-to-granary,
  scheduled meals, treasury aggregate sync) and must precede economy,
  which drains granaries for the dole
- industry (lumber mills + quarries → treasury, capped by total storage)
  precedes housing so the month's tier upgrades see the just-produced materials
- housing (monthly residence tier upgrades) precedes population so the
  same month's migration sees the bumped capacity

When adding a system, decide which side of `economy` it belongs.

## State shape

- **All mutable state lives on `GameState`** (`engine/world.py`). Off-tree
  state (live `random.Random`) is reconstructed at load via `RngState`.
- **One tick = one in-game hour.** Time constants in `engine/world.py`
  (`HOURS_PER_DAY`, `HOURS_PER_MONTH`, `HOURS_PER_YEAR`).
- **Schedule helpers** `is_first_of_month(tick)` and `is_first_of_week(tick)`
  in `engine/world.py` (both gate on `tick > 0`). Systems with monthly /
  weekly cadence call these instead of reinventing the modulo math.
- **Schema versioning**: bump `persistence/schema.py::SCHEMA_VERSION` whenever
  `GameState` shape changes incompatibly. No migration path in MVP — old
  saves should fail loudly.
- **`msgspec.Struct` typed fields**: construct with the declared type. An
  `int` passed to a `float` field will silently round-trip-coerce and
  break encode-byte-stability.

## Domain queries belong on the model

`City.is_buildable(x, y)`, `City.completed_of(kind)`,
`City.total_storage_capacity()`, `City.stored_materials()`,
`City.has_required_adjacency(kind, x, y)`, `City.can_afford` /
`City.pay_cost` live on the `City` struct — not as free functions in the
engine layer. Same for `Building`: `is_completed` / `is_under_construction`
properties replace scattered `b.completion >= 1.0` checks;
`residence_capacity()`, `operational_worker_slots()`, `farm_worker_slots()`,
`farm_worker_hours_per_harvest()`, `farm_yield_per_harvest()` are methods.
New systems should call these rather than reimplement the filter loop or
completion check.

## Spatial reach — one primitive

Granary / warehouse reach is a Dijkstra cost-12 walk computed in
`sim/systems/spatial.py::coverage`. The same primitive backs the grain
pipeline, the workshop / office reach checks, and the `i` info-screen
range highlight — never reimplement it in the UI, or the highlight will
drift from what the simulation uses. Roads cost 1/step vs ~2.5 for plain
ground, so paving extends reach dramatically.

## Removal — tombstones, not reindex

`_tombstone_building` clears the footprint tiles, drops the entry from
`district.building_ids`, and sets `b.kind = BuildingKind.EMPTY`. The
building stays in `city.buildings` so existing `tile.building_id`
references remain stable. Iterators that filter by kind (e.g.
`completed_of`, inspector renders) naturally skip EMPTY. **New systems
walking `city.buildings` must filter by kind to avoid touching tombstones.**

Two removal tools: UNDESIGNATE (free, only under-construction, 100%
refund) and BULLDOZE (`BULLDOZE_DENARII_COST` per building, refunds
`BULLDOZE_REFUND_FRACTION` of timber+stone; denarii are sunk).
Multi-tile (office) buildings remove as one unit.

## Multi-tile buildings

OFFICE is the only multi-tile building (2×2). All four
`tile.building_id` values point to the same `Building` struct so the
inspector resolves to that struct from any corner — no special
"find the anchor" code path. Cost is paid once. New multi-tile buildings
should follow the same shared-`building_id` pattern rather than
introducing per-tile shells.

## Two food pipelines, mirrored

Grain: wheat farms → `b.grain_stored` → granaries → `treasury.grain`.
Vegetables: vegetables farms → `b.vegetables_stored` → warehouses →
`treasury.vegetables`. Both use `spatial.coverage` for reach. Pleb meals
draw from both when both are in reach (50/50 split, with shortfall topping
up from the other side); patrician meals stay grain-only. Each meal that
meets demand from N distinct food types adds a small per-N satisfaction
bonus — the food-variety effect.

**Eat-from-farms fallback**: when an in-reach granary/warehouse can't
satisfy a meal, `grain._drain_for_house` falls through to draining
in-reach farms directly. Crucially, farm buffers stay out of
`treasury.grain` / `treasury.vegetables` — those mirror granary /
warehouse inventories only. A farm-fed meal must not move the treasury.
The dole drain (`drain_treasury_grain`) follows the same shape (granaries
first, then wheat farms, treasury sync still summing granaries only).

## Industry — local buffers + central treasury

Lumber mills hold up to `LUMBER_MILL_TIMBER_BUFFER` timber on the building
itself (`b.timber_stored`); quarries hold `QUARRY_STONE_BUFFER` stone
(`b.stone_stored`). Industry production lands in the treasury first
(capped by `total_storage_capacity()` from forum + warehouses); when the
treasury is full, output spills into the producing building's local buffer.
Production halts only when treasury *and* local buffer are both full.

`City.can_afford` / `City.pay_cost` combine treasury and every operational
mill/quarry buffer — paying timber drains treasury first then mills oldest
first; same for stone with quarries. `treasury.timber` / `treasury.stone`
track the central pool only, so the cap check stays honest. Bulldozing a
mill/quarry forfeits the local buffer.

**Industrial adjacency**: lumber mills require an orthogonally-adjacent
`FOREST` tile; quarries need adjacent `HILL` or `ROCK`. Enforced in
`_place_zone_rect`. Procgen-seeded buildings bypass this. Adjacency is
checked at placement only — bulldozing the adjacent forest later doesn't
shut the mill down.

**Industrial nuisance**: quarries and lumber mills emit nuisance within
`INDUSTRIAL_NUISANCE_RADIUS` (Chebyshev). Residences in that zone (a) cap
at huts (tier 1) regardless of office reach or materials, and (b) drag
district satisfaction down monthly. The kind set lives in
`housing.INDUSTRIAL_NUISANCE_KINDS`; add new dirty production kinds there.
Idle (zero-worker) industrial buildings still emit — gate is on
`is_completed`, not `workers_assigned`.

## Housing tiers

Tier-aware capacity via `Building.residence_capacity()`. Every consumer
(grain meal demand, migration cap, inspector display) routes through this
method. RESIDENCE is the building kind; tier 0/1/2/3 carry the actual
class ("undeveloped"/"huts"/"cottages"/"insula") via `RESIDENCE_TIER_NAME`.
Tier 1 needs only timber; tier 2+ needs timber AND stone. Reading
`RESIDENCE_TIER_CAPACITY[…]` directly bypasses the kind check and
desyncs systems.

**Two distinct road-proximity checks for residences**:
- `RESIDENCE_AMENITY_REACH_COST = 4.0` is a Dijkstra cost cap (over
  `spatial.coverage`) used by `housing._has_road_in_reach` to gate *tier
  upgrades* — only residences with a road reachable under cost 4 improve.
- `ROAD_DESIRABILITY_RADIUS = 2` is a literal Chebyshev tile-distance
  check used by `housing._apply_road_desirability` for the *monthly
  satisfaction bonus*.

**Cottages gate on office reach.** Tier 2 only upgrades if a completed
`OFFICE` covers the residence under `spatial.coverage` with reach
`OFFICE_REACH_PER_WORKER × workers_assigned`. An office with 0 workers
covers nothing. Tier 1 has no office gate; tier 3 keeps the existing
material+road gates.

**Tier cap**: residences carry `tier_cap`; housing stops upgrading once
`tier == tier_cap`. Default `tier_cap = RESIDENCE_MAX_TIER` is uncapped.
Lowering the cap below current tier never downgrades; only blocks further
upgrades.

## Economy

**Taxation is office-gated.** Plebs and patricians whose residence is
outside the union of all office coverages contribute zero tax. The grain
dole still applies to every pleb (it's a satisfaction expense, not a
range gate). `economy._office_taxable_pops` mirrors `_residence_occupancy`'s
pro-rating math so the inspector and the tax base never drift.

## Labor

`labor.step` groups every building into one of six `LaborCategory`
buckets via `labor_category_for(b)` — Construction (any
under-construction), Farms, Lumber mills, Quarries, Workshops,
Offices — then drains the per-district worker pool in
`city.labor_priority` order. Within a bucket, placement order
(`district.building_ids`) decides ties. Buildings without a bucket
(residences, granaries, warehouses, roads, civic) always land at
`workers_assigned == 0`. The priority list is mutated through
`SetLaborPriority` (must be a permutation of LaborCategory ints 0..5;
invalid input is silently dropped).

## Workshops

`Building.good` parallels `Building.crop` — value is a `Good` IntEnum
(FURNITURE, STONEWARE). Furniture consumes timber, stoneware consumes
stone, both produce into the treasury aggregate (`treasury.furniture` /
`treasury.stoneware`). Industry halts a workshop when input is
insufficient — no partial yields.

## UI conventions

- **Two hotkeys for the building under the cursor**: `i` opens
  `InfoScreen` (read-only detail, including per-source granary/warehouse
  listing for residences and the inventory graph hotkey for granaries);
  `c` opens `ConfigScreen` (mutates state via commands — farms set crop,
  residences set `tier_cap`, workshops set good).
- **Crop switch confirm**: switching past `CROP_SWITCH_CONFIRM_THRESHOLD`
  maturity prompts y/n since standing growth is discarded.
- **Escape clears the build tool last.** `app.action_cancel` cascades
  drag → range highlight → tool. Pressing escape with no drag and no
  highlight drops the active brush — Vim-style reset.
- **Rich markup must go through `style=` or `Text.from_markup`.** Never
  `text.append("[dim]…[/]")` — `Text.append` treats brackets as literal
  characters, so the markup leaks to the player. Either pass `style="dim"`
  as a kwarg or split into separate appends with their own styles. The
  `_assert_no_markup_leaks` helper in `test_config_screen.py` pins this
  for the config dialogs.

## Map / world
- Region: 32×32 tiles, ~5 km each (`world/procgen/region.py`).
- City: 60×30 tiles, ~30 m each (`world/procgen/city.py`).
- Both sizes are module constants; not configurable in MVP.

## Out of MVP scope (don't pull in unprompted)
Senate/cursus honorum, faction politics, market simulation, religion
beyond stubs, naval/siege warfare, multi-province empires, modding API,
z-levels. Each would shift architecture; surface them as proposals before
starting.
