# SPQR — Roman City Simulation Engine

Text/terminal city sim, Dwarf Fortress × SimCity, ancient-Roman themed.
The MVP is "engine first": deterministic tick loop, procgen world,
hybrid agent/aggregate population, Textual TUI.

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
- **Domain queries hang off the model.** `City.is_buildable(x, y)`,
  `City.completed_of(kind)`, `City.total_storage_capacity()`,
  `City.stored_materials()` live on the City struct — not as free
  functions in the engine layer. Same for Building:
  `b.is_completed`/`b.is_under_construction` properties replace the
  scattered `b.completion >= 1.0` checks; `b.residence_capacity()`,
  `b.operational_worker_slots()`, `b.farm_worker_slots()`,
  `b.farm_worker_hours_per_harvest()`, `b.farm_yield_per_harvest()`
  are methods, not free functions. New systems should call these
  rather than reimplement the filter loop or completion check.
- **Housing capacity is tier-aware** via
  `Building.residence_capacity()`. Every consumer (grain meal demand,
  migration cap, inspector display) routes through this method.
  RESIDENCE is the building kind; tier 0/1/2/3 carry the actual class
  ("undeveloped"/"huts"/"cottages"/"insula") via
  `RESIDENCE_TIER_NAME`. Tier 1 needs only timber; tier 2+ needs
  timber AND stone (`RESIDENCE_TIER_UPGRADE_TIMBER_COST` /
  `_STONE_COST`). Reading `RESIDENCE_TIER_CAPACITY[…]` directly
  bypasses the kind check and desyncs systems — same shape of bug as
  reimplementing `coverage`.
- **Farm output is crop-driven** via `Building.farm_worker_slots()`,
  `farm_worker_hours_per_harvest()`, and `farm_yield_per_harvest()`
  methods. WHEAT (1 worker, monthly cycle, 150 grain) ships to
  granaries; VEGETABLES (4 workers, ~5-day cycle, 80 yield) ships to
  warehouses. Labor and grain both route through these methods so a
  wheat farm correctly draws 1 worker.
- **Schedule helpers live on `engine/world.py`**:
  `is_first_of_month(tick)` and `is_first_of_week(tick)` (both gate on
  `tick > 0`). Systems with monthly or weekly cadence (housing,
  economy, population) call these instead of reinventing the modulo
  math, so the tick-0 skip stays consistent everywhere.
- **Removal is tombstone-based.** `_tombstone_building` clears the
  footprint tiles, drops the entry from `district.building_ids`, and
  sets `b.kind = BuildingKind.EMPTY`. The building stays in
  `city.buildings` so existing `tile.building_id` values remain
  stable. Iterators that filter by kind (e.g. `completed_of`,
  inspector renders, `_full_residence_ids`) naturally skip EMPTY.
  New systems that walk `city.buildings` should also filter by kind
  to avoid touching tombstones. Removal happens through two tools:
  UNDESIGNATE (free, only under-construction, 100% refund) and
  BULLDOZE (`BULLDOZE_DENARII_COST = 10` per building, refunds
  `BULLDOZE_REFUND_FRACTION = 0.5` of timber+stone, denarii are
  sunk). Multi-tile (office) buildings remove as one unit.
- **Industrial nuisance** caps residences. Quarries and lumber mills
  emit nuisance within `INDUSTRIAL_NUISANCE_RADIUS = 4` (Chebyshev).
  Residences in that zone (a) cap at huts (tier 1), regardless of
  office reach or materials, and (b) drag district satisfaction down
  by `INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH × fraction-of-residences-
  in-zone` each month. The kind set lives in
  `housing.INDUSTRIAL_NUISANCE_KINDS`; add new dirty production kinds
  there. Idle (zero-worker) industrial buildings still emit nuisance —
  the gate is on `is_completed`, not on `workers_assigned`.
- **OFFICE is a 2×2 building.** Placement requires all four tiles
  in the footprint anchored at (x1, y1) to be buildable; the engine
  clamps any wider PlaceZoneRect to 2×2 for OFFICE. Cost is paid
  once, not four times. All four tile.building_ids point to the same
  office struct, so the inspector resolves to that struct from any
  corner — no special "find the anchor" code path. The UI shows a
  green/red 2×2 footprint preview at the cursor when the OFFICE tool
  is active. New multi-tile buildings should follow the same pattern
  (shared building_id) rather than introducing per-tile shells.
- **Workshops are crop-mirror configurable.** `Building.good`
  parallels `Building.crop` — value is a `Good` IntEnum
  (FURNITURE=0, STONEWARE=1). Furniture consumes timber, stoneware
  consumes stone, both produce into the treasury aggregate
  (`treasury.furniture` / `treasury.stoneware`). Industry system
  halts a workshop when input is insufficient — no partial yields.
- **Cottages gate on office reach.** Tier 2 (cottages) only upgrades
  if a completed `BuildingKind.OFFICE` has the residence in its
  Dijkstra coverage. Reach is `OFFICE_REACH_PER_WORKER ×
  workers_assigned`, computed via `spatial.coverage` — same primitive
  as granaries and warehouses. An office with 0 workers covers
  nothing (idle administrative shell). Tier 1 (huts) has no office
  gate; tier 3 (insula) keeps just the existing material+road gates
  since cottages already required the office.
- **Taxation is office-gated.** Plebs and patricians whose residence
  is outside the union of all office coverages contribute zero tax.
  The grain dole still applies to every pleb (it's a satisfaction
  expense, not a range gate). `economy._office_taxable_pops` mirrors
  `_residence_occupancy`'s pro-rating math so the inspector and the
  tax base never drift.
- **Labor is bucket-prioritized.** `labor.step` groups every
  building into one of six `LaborCategory` buckets via
  `labor_category_for(b)` — Construction (any under-construction),
  Farms, Lumber mills, Quarries, Workshops, Offices — then drains
  the per-district worker pool in `city.labor_priority` order.
  Within a bucket, placement order (`district.building_ids`)
  decides ties. Buildings without a bucket (residences, granaries,
  warehouses, roads, civic) always land at `workers_assigned == 0`.
  The priority list is mutated through `SetLaborPriority` (must be
  a permutation of LaborCategory ints 0..5; invalid input is
  silently dropped) — same convention as `SetTaxRate` /
  `SetGrainDole`. Default order:
  `[CONSTRUCTION, FARMS, LUMBER_MILLS, QUARRIES, WORKSHOPS, OFFICES]`.
- **Eat-from-farms fallback.** When a residence's meal can't be
  satisfied by in-reach granaries / warehouses (after the cross-fill
  topup), `grain._drain_for_house` falls through to draining
  in-reach farms directly — wheat farms feed grain, vegetable farms
  feed vegetables. Farms reach houses under `FARM_TRANSPORT_REACH_COST`
  (the same Dijkstra cap they ship to granaries under, so reach is
  symmetric). Crucially, farm buffers stay out of `treasury.grain` /
  `treasury.vegetables` — those mirror granary / warehouse
  inventories only, and the dole + tax base read the cached
  aggregates. A farm-fed meal must not move the treasury.
  `drain_treasury_grain` (the dole drain) follows the same shape:
  granaries first, then wheat farms, with the treasury sync at the
  end still summing granaries only.
- **Mill / quarry local buffers.** Lumber mills hold up to
  `LUMBER_MILL_TIMBER_BUFFER` timber on the building itself
  (`b.timber_stored`); quarries hold `QUARRY_STONE_BUFFER` stone
  (`b.stone_stored`). Industry production lands in the city
  treasury first (capped by `total_storage_capacity` from forum +
  warehouses); when the treasury is full, output spills into the
  producing building's local buffer. Both pools halt production
  only when treasury *and* the local buffer are full.
  Construction goes through `City.can_afford` / `City.pay_cost`,
  which combine the treasury and every operational mill / quarry
  buffer — paying timber drains treasury first, then mills oldest
  first; same for stone with quarries. Treasury sync (`treasury.timber`
  / `treasury.stone`) tracks the central pool only, so the cap
  check stays honest. Bulldozing a mill / quarry forfeits the
  local buffer (matches farms losing `grain_stored` on bulldoze).
- **Mill / quarry adjacency.** Lumber mills only place on tiles
  with at least one orthogonally-adjacent `CityTerrain.FOREST`;
  quarries need adjacent `HILL` or `ROCK`. Enforced by
  `City.has_required_adjacency(kind, x, y)` in `_place_zone_rect`.
  Procgen-seeded buildings bypass the engine path and aren't
  subject to the rule (the starter block still ships with mill /
  quarry on grass). Adjacency is checked at placement time only —
  if the adjacent forest is later bulldozed, the mill keeps
  producing on the now-empty land, same as a real-world land-use
  grandfather clause.
- **Escape clears the build tool last.** `app.action_cancel`
  cascades drag → range highlight → tool. Pressing escape with no
  drag and no highlight active drops the active brush
  (`_zone_tool`) back to None — Vim-style reset. Selecting a tool
  via the build menu sets the brush; the only ways to clear it are
  picking another tool or escape with a clean slate.
- **Two food pipelines, mirrored.** Grain: wheat farms →
  `grain_stored` → granaries → `treasury.grain`. Vegetables: veg farms
  → `vegetables_stored` → warehouses → `treasury.vegetables`. Both use
  the same `spatial.coverage` reach. Pleb meals draw from both when
  both are in reach (50/50 split, with shortfall topping up from the
  other side). Patrician meals stay grain-only. Each meal that meets
  demand from N distinct food types adds `0.003 × N` to district
  satisfaction — the food-variety desirability bonus.
- **Two distinct road-proximity checks for residences.** Don't conflate
  them. (a) `RESIDENCE_AMENITY_REACH_COST = 4.0` is a Dijkstra cost cap
  (over `spatial.coverage`) used by `housing._has_road_in_reach` to gate
  *tier upgrades* — only residences with a road reachable under cost 4
  improve to huts/cottages/insulae. (b) `ROAD_DESIRABILITY_RADIUS = 2`
  is a literal Chebyshev tile-distance check used by
  `housing._apply_road_desirability` for the *monthly satisfaction
  bonus* — every residence within 2 tiles of a road contributes
  `ROAD_DESIRABILITY_BONUS_PER_MONTH` × (fraction-with-road) to district
  satisfaction, smooth across partial coverage.
- **Two hotkeys, two screens, two purposes** for the building under the
  cursor. (i) opens `InfoScreen` — read-only detail, including the
  per-source granary/warehouse listing for residences and the inventory
  graph hotkey for granaries. (c) opens `ConfigScreen` — mutates state
  via commands. Farms configure crop (switching past
  `CROP_SWITCH_CONFIRM_THRESHOLD = 0.30` maturity prompts y/n
  confirmation since standing growth is discarded). Residences
  configure `tier_cap`: the housing system stops upgrading once
  `tier == tier_cap`, freezing a plot at undeveloped/huts/cottages
  even when materials and roads would advance it further. Default
  `tier_cap = RESIDENCE_MAX_TIER` means uncapped. Lowering the cap
  below the current tier never downgrades; it only blocks further
  upgrades.
- **Rich markup must go through `style=` or `Text.from_markup`.** Never
  `text.append("[dim]…[/]")` — `Text.append` treats brackets as
  literal characters, so the markup leaks to the player verbatim.
  Either pass `style="dim"` as a kwarg or split into separate appends
  with their own styles. The `_assert_no_markup_leaks` helper in
  `test_config_screen.py` pins this for the config dialogs.
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
- **Do not run `pytest` or the headless determinism check unless the
  user explicitly asks.** They run frequently enough during the user's
  own workflow that re-running them autonomously after every change is
  noisy and slow. Write tests, leave them for the user to run.
- For TUI changes: `app.run_test()` pilot test with `pilot.press(...)`
  and assertions on `engine.state` (see how the smoke checks were
  written in the JOURNAL session) — same rule, write but don't run.

## Out of MVP scope (don't pull in unprompted)
Senate/cursus honorum, faction politics, market simulation, religion
beyond stubs, naval/siege warfare, multi-province empires, modding API,
z-levels. Each would shift architecture; surface them as proposals
before starting.
