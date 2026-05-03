# SPQR Engine Journal

Running log of what was built, what worked, and what bit us. Append-only;
new entries on top.

---

## 2026-05-03 — Residence rename, material tiers, lumber mill + quarry

Three changes shipped together; schema bumped to v6.

### Renames
- `BuildingKind.HOUSE` → `BuildingKind.RESIDENCE`. ZoneKind, all
  HOUSE_* constants, and the `house_capacity` helper renamed in
  parallel. The substring rename had a sharp edge — `WAREHOUSE`
  matches `HOUSE`, and a naive replace_all turned it into
  `WARERESIDENCE`. Caught and reverted; subsequent edits used
  targeted patterns instead.

### Tier mechanics
- Tier 0 (undeveloped) capacity: 2 → 3.
- Tier 2 (cottages) and tier 3 (insula) now require BOTH timber AND
  stone via the new `RESIDENCE_TIER_UPGRADE_STONE_COST` table:
  `{1: 0, 2: 10, 3: 25}`. Housing system pays both via
  `Resources(timber=…, stone=…)` — `treasury.can_pay`/`pay` already
  handle multi-resource costs uniformly.
- Tier 1 (huts) still needs timber only, matching the user's
  "huts requires wood" call.

### Industry
- New BuildingKinds: `LUMBER_MILL` (10) and `QUARRY` (11).
  - LUMBER_MILL: 80d / 0t / 10s. **No timber to build** — that's the
    bootstrap loop the user wanted: you can build the first mill from
    starter stone alone.
  - QUARRY: 100d / 20t / 0s. Needs timber, so order is: spend starter
    timber on a lumber mill → mill produces timber → use that timber
    to build a quarry → both flow into warehouses.
- New `sim/systems/industry.py`. Per-tick: each operational mill /
  quarry adds `rate × workers_assigned` to `treasury.timber` /
  `treasury.stone`. Production halts when
  `treasury.timber + treasury.stone >= total_storage_capacity`. This
  is what "yields are stored in warehouse" means in practice — without
  warehouse storage, production stops.
- Rates: `LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK = 0.05`,
  `QUARRY_STONE_PER_WORKER_PER_TICK = 0.04`. At full staffing
  (2 workers) that's 2.4 timber/day, 1.92 stone/day. Tunable from
  `sim/models/building.py`.

### UI
- Build menu adds hotkeys `7` (lumber mill) and `8` (quarry).
- Inspector renders the production rate and storage-cap status for
  mill / quarry. The "production halted" tag appears in red when at
  cap so the player can see when more warehouses are needed.
- Map glyphs: `L` (yellow) for lumber mill, `Q` (grey) for quarry.

---

## 2026-05-03 — Vegetables in warehouses + food-variety bonus

Closes the vegetables loop and adds the first real "desirability"
mechanic: houses with access to both grain *and* vegetables grow
satisfaction (and therefore migration) twice as fast as grain-only.

### Changes
- `Resources.vegetables: float = 0.0` and `Building.vegetables_stored:
  float = 0.0` added. Schema bumped to v5.
- New `WAREHOUSE_VEGETABLES_CAPACITY = 1000.0` (vs granary's 3000 —
  vegetables are the supplement, not the staple).
- `grain.py` extended:
  - `_grow_and_harvest`: vegetables farms now produce, dropping yield
    into `farm.vegetables_stored` instead of `farm.grain_stored`.
  - `_transport`: a generalized `_nearest_storage_for_farm` handles
    both wheat→granary and veg→warehouse routing.
  - `_warehouse_coverages` mirrors `_granary_coverages` using the
    same `GRANARY_REACH_COST = 12.0` Dijkstra cap.
  - `_consume`/`_serve_meal`/`_drain_for_house`: pleb meals now split
    50/50 between grain and vegetables when both are in reach with
    stock; if one source under-delivers, the other tops up the
    shortfall. Patrician meals stay grain-only (`allow_veg=False`).
- `_serve_meal` returns `(unmet, food_types_drawn)`, which
  `_apply_meal_satisfaction` uses to scale the success bonus:
  `+0.003 × food_types`. So a district drawing from both sources
  gains satisfaction at 2× the rate of a grain-only district.
- `_sync_treasury_vegetables` mirrors `_sync_treasury_grain`.
- Inspector adds: warehouse veg stock, veg-farm "in transit", and a
  per-house "Food types: N" line so the player can see when the
  variety bonus kicks in.

### Design choices to revisit
- Patricians stay grain-only — easy to extend later.
- 50/50 split when both food types accessible — could weight by
  proportional stock or always grain-first.
- Variety bonus is linear in food-type count. Once more food kinds
  exist (meat? fruit?), might want diminishing returns.

---

## 2026-05-03 — Crops + house-tier rename + weekly migration

Three player-facing changes shipped together; all force a schema bump
to v4. Old saves fail loudly per the existing invariant.

### Crops
- New `Crop` IntEnum {WHEAT=0, VEGETABLES=1}. `Building.crop: int = 0`
  added; meaningful only on FARM.
- Per-crop tunings live in `CROP_WORKER_SLOTS`,
  `CROP_WORKER_HOURS_PER_HARVEST`, `CROP_YIELD_PER_HARVEST`. Wheat:
  1 worker, 720 worker-hours per harvest (= 1 harvest/month at full
  staffing), 150 grain yield. The yield is calibrated so one wheat
  farm sustains one tier-1 (huts, 6 plebs) house year-round even
  accounting for the 7-month growing season: 7 × 150 = 1050 grain/yr
  vs. 6 × 0.48 × 365 ≈ 1051 demand.
- Vegetables stub: 4 workers, ~5-day cycle, 80 yield. **Currently
  produces no consumable** — buildable and switchable but the grain
  pipeline ignores it. TODO: define a vegetables consumer (likely
  satisfaction/variety bonus) once the player loop is solid.
- New `SetFarmCrop(building_id, crop)` command. Wired through
  `engine/tick.py`; switching crops resets `grain_maturity` (different
  planting cycles). Exposed in the info screen as `c` hotkey.
- `labor.py` switched from `WORKER_SLOTS.get(b.kind, 0)` to
  `operational_worker_slots(b)`, which is FARM-aware (delegates to
  `farm_worker_slots(b)` based on crop). WORKER_SLOTS no longer has
  a FARM entry — keeping it in there would have been a footgun.

### House tier rename
- `BuildingKind.INSULA` → `BuildingKind.HOUSE`. ZoneKind.INSULA →
  ZoneKind.HOUSE. INSULA_* constants → HOUSE_*. `Insula` was retained
  as a tier *display name* (HOUSE_TIER_NAME[3] = "insula").
- New tier table: {0: 2 (undeveloped), 1: 6 (huts), 2: 15 (cottages),
  3: 40 (insula)}. Tier upgrade timber costs recalibrated to match:
  {1: 5, 2: 20, 3: 50}.
- Inspector renders the tier name (e.g. "huts, tier 1/3") and the
  farm crop (e.g. "Sown with: wheat").

### What was reused
- `house_capacity()` invariant still holds — every consumer continues
  to route through it. Just got recalibrated; no consumer-side changes
  needed beyond the rename.
- `spatial.coverage` reused unchanged for the road-amenity check.

---

## 2026-05-03 — Weekly immigration waves

Migration was monthly (HOURS_PER_MONTH gate), which made the early
game feel empty — at default sat=0.6, only 3 plebs/month, taking ~16
months to fill 6 tier-0 houses (12 capacity).

### Changes
- New `HOURS_PER_WEEK = 168` constant in `engine/world.py`.
- `population.py::step` split: weekly migration block, monthly births/
  deaths/unrest. Both early-return on tick==0.
- `MIGRATION_BASE_RATE = 5.0` retained but now per-week, so effective
  inflow at sat=0.6 is ~3 plebs/week (4× the old monthly rate).
- Out-migration rate rescaled to 0.0125/week (= 5%/month) so a
  starving district drains at the same long-run pace as before — only
  the inflow cadence changed in the player-visible direction.

---

## 2026-05-03 — Fresh-terrain start, migration-driven pop, insula tiers

Pivot the early game from "manage an inherited city" to "found one from
nothing." Schema bumped to v3; old saves fail loudly per the existing
invariant.

### Changes
- `world/procgen/city.py` no longer seeds the forum, four insulae, three
  farms, or the granary. Starter district owns no buildings. Pops start
  at `PopPool(plebs=0, patricians=0)`. Treasury keeps `500d/80t/40s`,
  enough for one INSULA + a granary + a couple of farms.
- `Building` gets a `tier: int = 0` field. `INSULA_TIER_CAPACITY =
  {0:8, 1:20, 2:40, 3:60}`, `INSULA_TIER_UPGRADE_TIMBER_COST =
  {1:10, 2:20, 3:30}`, `INSULA_AMENITY_REACH_COST = 4.0`. New helper
  `house_capacity(b)` is the single tier-aware lookup; CLAUDE.md gets
  an invariant for it parallel to the `coverage` invariant.
- INSULA designation cost drops to `50d/0t/0s` (lumber is reserved for
  upgrades). In `engine/tick.py::_place_zone_rect`, INSULA is
  special-cased to `completion=1.0` — tier-0 plots are tents, no
  construction time.
- New `sim/systems/housing.py`: monthly per-insula tier upgrade if a
  road is within `INSULA_AMENITY_REACH_COST` of the house tile (via
  `spatial.coverage`) and the treasury has timber. Registered between
  `grain` and `economy` in `default_systems`, so the same month's
  migration sees the bumped capacity.
- `sim/systems/population.py` migration: replace the satisfaction-only
  inflow/outflow with capacity-gated migration. Open slots = sum of
  `house_capacity` over completed insulae minus current plebs;
  `inflow = min(open_slots, MIGRATION_BASE_RATE * sat)` per month
  (where `MIGRATION_BASE_RATE = 5.0`). Below `sat = 0.3` or with no
  open slots, plebs flow out. Births/deaths untouched (no-op at 0
  pop, ambient growth once seeded).
- `sim/systems/grain.py` meal demand distribution switched from
  `HOUSING_CAPACITY[INSULA]` to `house_capacity(h)` so tier-bumped
  capacity flows through to per-house meal share.
- Inspector renders the insula tier and tier-adjusted capacity.

### Out of scope (deferred)
- Fountains/aqueducts/water amenities — only road counts as amenity for
  now. All tiers currently demand only "road within reach"; future
  tiers will demand water and civic buildings to differentiate them.
- DOMUS in build menu / patrician migration. The DOMUS branch in code
  is harmless (it just stays at 0 pop forever).
- Tier degradation if amenities removed — one-way upgrades.

---

## 2026-05-02 — MVP simplification: peaceful builder, two-tier population

Cut the agents and military layers entirely so MVP focuses on pool-based
demographics and peaceful building. Schema bumped to v2; old saves fail
loudly per the existing invariant.

### Changes
- `PopClass` reduced from {SLAVE, PLEB, EQUES, PATRICIAN} to {PLEB,
  PATRICIAN}; `PopPool` fields collapse to `plebs / patricians / unrest`.
  Meal dicts re-keyed to `0=PLEB, 1=PATRICIAN`.
- Deleted `sim/systems/agents.py`, `sim/systems/military.py`, and
  `sim/systems/events.py` (events.py was 100% raid-driven). Default
  system list shrinks to labor → construction → grain → economy →
  population.
- Deleted `Citizen` / `CitizenRole` model and `GarrisonState`. `City`
  drops `citizens` / `next_citizen_id` / `garrison`.
- Removed `BuildingKind.BARRACKS` (and its housing/cost/storage entries),
  `LEGIONARY_*` constants, `hours_until_legionary_meal`, the legionary
  branch in `grain._consume`, and the garrison-upkeep block in
  `economy.step`. Tax brackets simplified: just plebs and patricians (8x).
- Region procgen drops `_place_barbarians` and the barbarian-camp →
  city Bresenham road. `SiteKind.BARBARIAN_CAMP` removed; only
  PLAYER_CITY left in the enum. `NeighborSite` loses `aggression` /
  `strength`. Province now only ever contains the player's own site.
- UI cleanup: dropped the `[3] Barracks` build-menu entry, the `legion N`
  status-bar field, the BARRACKS map glyph, the BARBARIAN_CAMP region
  glyph, and the slave/eques rows in the population screen.

### What worked
- The schema-version invariant did its job: old saves are rejected on
  load because `SCHEMA_VERSION` bumped to 2; no migration code needed.
- Determinism preserved end-to-end. After all the procgen/system cuts,
  `--headless --seed 42 --ticks 1000 --hash-only` is stable across runs
  (`b25897fb…`). The hash naturally differs from the pre-cut value, but
  reproducibility is what matters.
- Re-keying `MEAL_*` dicts to the new `PopClass` ordinals (PLEB=0,
  PATRICIAN=1) was clean because `int(PopClass.X)` is the lookup key
  everywhere — only 5-line edit in `building.py` plus the iteration
  tuple in `grain._consume`.

### What didn't / lessons
- Two `test_grain` / `test_population` tests broke because the procgen
  RNG sequence shifted (no more BARRACKS placement → insulae land in
  different tiles). With the new layout only 2 of 4 insulae sat in the
  starter granary's reach, so meal demand was half-served and
  satisfaction crashed. Lesson: tests that depend on procgen layout for
  spatial-reach behavior are brittle — fixed by stripping insulae from
  the district's `building_ids` so meals fall back to
  `_drain_any_granary` (location-independent). For future tests
  involving meals, prefer the fallback path unless you're explicitly
  testing reach.
- Killing barbarians removed the only consumer of the `events` system,
  so `events.py` went too. If we add fires / plagues / festivals later,
  they slot back in at the same point in the system order with the
  same monthly-tick cadence.

---

## 2026-04-25 — Advanced (i)nfo: granary range highlight + inventory graph

Added an `i` hotkey on the main view that opens an `InfoScreen` for the
building under the cursor. For granaries the screen exposes two further
actions: `r` highlights the granary's coverage on the city map (teal
background tint), and `g` opens a `GraphScreen` showing inventory
history over time. The graph supports `d` to toggle between hourly
resolution (last ~60h) and daily resolution (avg per day, up to 30
days).

### Changes
- `Building` gained `inventory_history: list[float]` (default empty);
  `grain.step._record_granary_history` appends each granary's
  `grain_stored` per tick. Capped at `GRANARY_HISTORY_MAX_SAMPLES = 720`
  (30 game days). msgspec serializes lists fine — no schema bump.
- New `src/spqr/ui/screens/info.py`:
  - `InfoScreen(state, building_id)` → `ModalScreen[InfoResult]`.
    Dispatches by building kind: granaries get range/graph hotkeys,
    other kinds get a generic detail pane.
  - `InfoResult` is a small dataclass with three "kinds": `close`,
    `highlight`, `graph` — replaced an earlier sentinel-object draft.
  - `GraphScreen(state, building_id)` renders a sparkline-style ASCII
    bar chart using Unicode block characters quantized to 9 levels.
    Refreshes at 2 Hz so the chart updates while the sim runs.
- App (`src/spqr/ui/app.py`) gained:
  - `Binding("i", "action_info", "Info")`
  - `_range_highlight: frozenset[(x,y)] | None` plus owner id
  - `_set_range_highlight(granary_id)` runs the same `coverage()`
    Dijkstra used by the grain system.
  - `escape` is now a unified `action_cancel` with priority:
    drag → range highlight → no-op.
- `CityMap.range_highlight` field, propagated into `_render_city`.
  Teal background sits below the drag preview rect and the cursor in
  z-order, so dragging or moving the cursor doesn't lose the highlight.

### What worked
- Reusing `coverage()` for both the grain system's internal use and
  the visualization meant zero risk of "the highlight shows a
  different reach than the simulation actually uses." That's an
  always-true invariant; tests for one verify the other.
- Storing inventory history on the Building struct (rather than a
  side-car dict on GameState) keeps locality and lets msgspec persist
  it without any per-field plumbing.
- Live-refreshing modals (set_interval at 2 Hz) means a graph stays
  interesting while the player watches the city eat. Good for
  debugging too — open the graph, run at 64×, see the staircase.

### What didn't / lessons
- First draft used `dismiss(ZoneKind | _CancelSentinel)` style for
  InfoScreen — same anti-pattern from the build menu. Replaced with
  `InfoResult(kind, granary_id)`. Lesson re-learned: if the modal has
  more than one "result type", a small dataclass beats a sentinel
  every time.
- Range highlight clears via `escape`, but `escape` also cancels
  drag. Initial implementation only handled drag. Promoted `escape`
  to a single `action_cancel` that walks a priority list (drag →
  highlight → nothing). Predictable and easy to extend.

### Tests added
- `test_granary_history_records_per_tick` — one sample per step.
- `test_granary_history_caps_at_max_samples` — old samples evicted.
- `test_render_granary_info_lists_served_buildings`
- `test_render_graph_hourly_mode`
- `test_render_graph_daily_mode_aggregates_24h_chunks` — 72 ticks
  yield 3 daily aggregates.
- `test_render_graph_handles_empty_history`
- `test_info_result_is_a_three_state_enum`

---

## 2026-04-25 — Meals are scheduled events, not continuous drain

User reported "grain seems to decrease constantly." That was the visible
artifact of `_consume` running every tick at hourly aggregate rates.
Switched to discrete meal events on a per-class schedule:

- Slaves: every 48 h (offset 5 — every other dawn)
- Plebs: every 24 h (offset 6 — daily breakfast)
- Equites: every 12 h (offset 7 — 7 am, 7 pm)
- Patricians: every 12 h (offset 9 — 9 am, 9 pm)
- Legionaries: every 12 h (offset 6 — mess hours)

Tick check: `(tick - offset) % interval == 0`. Per-meal grain is
calibrated so daily totals match the old hourly rates exactly (e.g.
plebs 0.48 grain/meal × 1 meal/day = 0.48/day = 0.020/h, same as before).
Soldiers were previously a token 5 grain/month for the entire garrison;
they now eat ~120 grain/month for 10 troops, drawing from granaries
serving the barracks.

### What worked
- Reusing the existing `_drain_for_house` / `_drain_any_granary`
  primitives meant the new pipeline only needed a meal-tick check at
  the top, plus a per-class housing kind lookup. The spatial reach
  helper `coverage()` was already shape-correct.
- Calibrating per-meal grain to preserve daily totals kept overall
  balance unchanged for civilians while letting the inspector tell a
  meal-frequency story.
- New `hours_until_next_meal(tick, cls)` helper drives the inspector
  "Pleb meal: in 7h" line. Same module exposes
  `hours_until_legionary_meal(tick)` for the barracks panel.

### What didn't / lessons
- **Engine increments tick before running systems**, so a meal at
  tick==6 fires during the step that advances *5→6*. Both new tests
  initially asserted a drop after `state.tick` reached 6 via stepping
  to it; they had to be rewritten to step until tick==5 then take one
  more step. Worth pinning in CLAUDE.md as a load-bearing invariant —
  any "this fires on tick T" check needs to be stepped *to* T-1 first.
- The granary trace showed drops of ~26 grain at hour 6 (instead of
  expected 24 for plebs alone). That's the legionary mess (×0.20
  grain × 10 = 2) firing on the same tick because both classes have
  offset 6. Correct, but worth noting in the test as "pleb +
  legionary co-fire."
- Removed the old `GRAIN_PER_LEGIONARY_MONTH = 0.5` block from
  `economy.py::_apply_monthly`. Soldiers now eat exclusively through
  the meal pipeline; double-charging would have over-drained the city
  by 2 grain/legionary every month.

### Tests added
- `test_meal_event_fires_only_on_scheduled_tick`
- `test_legionary_meal_drains_granary`
- `test_grain_inventory_is_a_staircase_not_a_slope` — counts distinct
  drop events over 24 ticks; expects 1–8 (the actual rhythm has 5–6).

---

## 2026-04-25 — Construction sites flash glyph/terrain

Under-construction tiles now alternate between the building glyph (dim)
and the underlying terrain glyph at 1 Hz (0.5 s per phase). Period is
wall-clock based via `time.monotonic()`, so the flash continues even when
the sim is paused. Determinism unaffected — rendering doesn't feed back
into game state.

`_render_city` gained a keyword-only `flash_show_building` parameter so
tests can pin a phase deterministically (`test_map_view.py`). In
production, `CityMap.render` lets it default to None, which derives the
phase from the wall clock.

---

## 2026-04-25 — Seasonal grain pipeline (growth, transport, proximity feeding)

Replaced the flat hourly grain production/consumption math with a real
spatial pipeline. The headline change: there is no longer a single
city-wide grain pool. Granaries hold grain. Farms grow grain. Houses
eat from granaries within walking distance.

### What changed
- New fields on `Building`: `grain_maturity` (0..1, only meaningful on
  farms) and `grain_stored` (used by farms and granaries). Backward
  compatible — defaults are 0.0, old saves load fine.
- New constants in `sim/models/building.py`:
  `GROWING_SEASON_MONTHS = {3..9}`,
  `FARM_WORKER_HOURS_PER_HARVEST = 2880`,
  `GRAIN_YIELD_PER_HARVEST = 600`,
  `FARM_GRAIN_CAPACITY = 1200`,
  `GRANARY_CAPACITY = 3000`,
  `GRANARY_REACH_COST = 12`, `FARM_TRANSPORT_REACH_COST = 16`,
  per-class `MEAL_INTERVAL_HOURS` and `GRAIN_PER_MEAL`.
- New file `sim/systems/spatial.py`: small Dijkstra over the city
  tilemap with road tiles cost 1, plain tiles 2.5, building tiles 2,
  water/rock impassable. Returns `{(x,y): cost}` reachable from a
  start tile within a cost cap. Deterministic (heapq + fixed neighbor
  order).
- New file `sim/systems/grain.py`: full pipeline.
  1. Growth: each tick during growing season, farms with workers
     advance `grain_maturity` by `workers / 2880`.
  2. Harvest: at maturity 1.0, drop `GRAIN_YIELD_PER_HARVEST` into
     `farm.grain_stored`, reset maturity. Logged.
  3. Transport: each farm with stored grain ships
     `GRAIN_TRANSPORT_RATE = 8` per tick to its nearest in-range
     granary that has capacity.
  4. Consume: each district's hourly demand (per-class rate × pop) is
     split by housing capacity across civilian buildings (insulae,
     domus); each house pulls its share from granaries that include
     its tile in their coverage.
  5. Sync: `treasury.grain` is recomputed as the sum of granary
     inventories and is now a derived display value.
- `sim/systems/economy.py` shrank: hourly grain math gone. Monthly
  taxation, garrison upkeep, and grain dole still here, but upkeep
  and dole now drain via `grain.drain_treasury_grain` (which empties
  granaries largest-first).
- System order: `labor → construction → grain → economy → ...`. Grain
  must run after labor (needs `workers_assigned`) and before economy
  (so the monthly dole/upkeep see fresh granary state).
- `procgen/city.py`: starter granary now seeded with 2500 grain
  (treasury.grain stays as a cached aggregate, set to match).
- Inspector: farms show maturity bar, season, awaiting-transport
  amount, yield/harvest. Granaries show inventory/capacity. Insulae
  and domus show in-range granary count + grain available, plus
  resident class and meal cadence.

### What worked
- Cost rates were chosen to **preserve aggregate hourly consumption**
  exactly: `grain_per_meal / meal_interval_hours` equals the old
  per-class hourly rates (e.g. plebs: 0.24/12 = 0.020). This kept
  balance roughly equivalent while letting the inspector tell a
  meal-frequency story.
- Splitting the spatial reach into its own module (`spatial.coverage`)
  let me reuse it from inspector tests and from both transport and
  consumption without duplication.
- Single source of truth (granaries) with a cached `treasury.grain`
  aggregate kept the status bar / population screen working without
  changing those widgets.

### What didn't / lessons
- A balance test (`test_pops_shrink_on_starvation`) used to disable
  farms by setting `completion = 0.0`. With the labor system now
  treating that as "needs builders", the construction system rebuilt
  the farms within a week and grain returned. Updated the test to
  starve the city in winter (off-season) so no farm can produce
  regardless of completion. Lesson: zeroing `completion` is no longer
  a way to "remove" a building from the sim — labor will rebuild it.
- First balance pass had `GRANARY_CAPACITY = 800` and starter stock
  of 2500 grain; the inspector immediately showed `2500 / 800` (cap
  violated, since `_sync_treasury_grain` doesn't enforce cap on save
  data). Bumped cap to 3000 for now. Late-game cities still want
  multiple granaries for *spatial reach*, not just capacity.
- Per-tick cost jumped from ~6 ms / 1000 ticks to ~160 ms (still well
  under the 2 s budget). Two Dijkstra passes per tick: one per
  granary (for coverage) and one per farm with stored grain (for
  transport target). Could cache by invalidation when buildings
  change; deferred until perf actually bites.
- Iteration-order quirk: in `_transport`, farms ship in `building_id`
  order. With one granary at cap, the lowest-id farm always drains
  first; later farms accumulate up to `FARM_GRAIN_CAPACITY` and only
  drain after the early farms are empty. Visible in playtraces — not
  wrong, just an ordering artifact. Round-robin or "drain fullest
  farm first" would be more elegant; defer.

### Tests added
- `test_farms_do_not_grow_outside_growing_season`
- `test_farm_grows_and_harvests_during_season`
- `test_harvest_yield_lands_in_granary_via_transport`
- `test_drain_treasury_grain_pulls_from_granaries`
- `test_coverage_extended_by_roads` — confirms paving roads visibly
  expands a granary's reachable tile set.

---

## 2026-04-25 — Construction now costs labor + materials + denarii

Made building no longer free — designation now pays an upfront cost in
denarii + timber + stone, and construction requires builders pulled from
the same workforce that staffs operational buildings.

### Changes
- New tables on `sim/models/building.py`:
  - `BUILDING_COST` — `Resources` per kind (e.g. farm = 20d/10t).
  - `BUILDER_SLOTS` — labor needed during construction (1 for farm/road,
    up to 4 for forum/temple).
  - `BUILD_HOURS` — total builder-hours; wall-clock = `BUILD_HOURS / builders`.
  - `STORAGE_CAPACITY` — materials stockpile per building. Forum 100,
    barracks 50, warehouse 250. Other kinds = 0.
- New `BuildingKind.WAREHOUSE` (kind=10) and `ZoneKind.WAREHOUSE` (=6).
  Glyph `S` (cyan) on the city map; entry `7` in the build menu.
- `engine/tick.py::_place_zone_rect` now `treasury.pay(cost)` per tile
  and skips tiles the city can't afford. Partial-rectangle placement is
  the rule, with a "skipped: treasury empty" tail in the log.
- `engine/tick.py` exposes `total_storage_capacity(city)` and
  `stored_materials(city)` helpers used by the inspector.
- `sim/systems/labor.py` now allocates builders to under-construction
  sites in addition to operators on completed buildings — both pull
  from the same `district.pops.workers()` pool.
- `sim/systems/construction.py` now `completion += workers_assigned /
  BUILD_HOURS[kind]` per tick. Zero builders → zero progress (stalled).
- **System order flipped**: labor must run before construction so the
  builder count is up to date when construction reads it. New order:
  `labor → construction → economy → ...`.
- Inspector now shows builder count + "stalled — no labor" warning
  during construction, and storage capacity + city-wide stocks for
  storage-bearing buildings.
- Build menu lists costs as `20d 10t` etc.

### What worked
- Re-using the existing `treasury: Resources` field for materials meant
  no schema change. The `Resources.can_pay` / `Resources.pay` helpers
  fit perfectly — they were written for exactly this.
- Upfront-pay model is much simpler than drip-pay: one branch in
  `_place_zone_rect`, no per-tick "is the truck unloading yet" state.
- Letting builders and operators share `workers_assigned` on the
  Building struct (semantics depend on completion < 1.0) avoided
  adding a new field. The labor system is the only thing that has to
  be careful about which one it's setting.

### What didn't / lessons
- A test asserted `completion >= 1.0` after exactly 168 ticks for a
  farm with 1 builder and 168 build-hours. Floating-point: 168 ×
  (1/168) = 0.9999999999999976. Stepped 170 to absorb drift; the
  `min(1.0, ...)` clamp fires on the next tick. (Could also `>= 0.999`
  but the extra tick is honest.)
- A test was written before the cost system that placed a 60-tile
  farm rectangle and asserted full coverage. Updated it to grant the
  treasury 10k of everything to isolate buildability from
  affordability. Added a separate test that confirms partial
  placement under treasury constraints.
- No way yet to **produce** timber or stone — lumberyards / quarries
  are next-milestone work. Players will run out and not be able to
  build more until that lands. Logged here so we don't forget.

### Tests added
- `test_place_zone_rect_skips_unaffordable_tiles` — partial placement.
- `test_place_zone_debits_treasury` — exact cost deduction for warehouse.
- `test_construction_stalls_without_workforce` — completion stuck at 0.
- `test_construction_uses_builder_slots_and_advances` — full progress
  with 1 builder + 168 build-hours.
- `test_total_storage_capacity_grows_when_warehouse_completes` —
  capacity computed only over completed buildings.

---

## 2026-04-25 — Build menu + population screen

- Moved the brush hotkeys (`1`–`6`, `0`) off the root key map and behind
  a modal **build menu** opened with `b`. Inside the modal the same
  keys arm the corresponding tool; `0` explicitly clears it; `escape`,
  `b`, or `q` leave the menu without changing the current tool.
- Cancel design: `BuildMenuScreen.__init__(current)` takes the active
  tool, and `action_cancel` dismisses with that value. The App callback
  short-circuits when `new_tool == self._zone_tool`. No sentinel object,
  no special-case "cancel" type. (An earlier draft used a `_CANCEL`
  sentinel; the constructor-passed-current-tool design replaced it.)
- Added a **population screen** opened with `p` (`PopulationScreen`).
  Modal, refreshes at ~5 Hz so values move while the sim ticks. Shows
  composition (by class), labor (workforce / slots / assigned / idle),
  housing (civilian pop vs. capacity, homeless count), and per-district
  satisfaction/unrest with red/yellow/green coloring.
- Status bar's tool-name field is unchanged — it already showed the
  armed brush, so the build-menu refactor only affects how you select
  the brush, not how it's surfaced.

### What worked
- Textual `ModalScreen[T]` with `push_screen(screen, callback)` is a
  clean fit for the build menu — the App stays single-screen and the
  callback hands back exactly the result type we want.
- Headless smoke via `app.run_test` + walking `app.screen_stack` made
  it easy to assert "modal mounted" / "modal dismissed" without any
  visual scaffolding. Same harness also reads the rendered `Text` from
  the population body to validate computed numbers.

### What didn't / lessons
- Initially wrote `text.append("[dim]...[/]")` on a plain Rich `Text`
  inside `_render_report`. Markup tags don't expand on `append` — they
  render as literal `[dim]` brackets. Fix: pass `style="dim"` instead,
  or use `Text.from_markup`.
- First draft of `BuildMenuScreen` used a `_CANCEL` sentinel object
  passed alongside `ZoneKind | None` to distinguish "cancelled" from
  "explicitly cleared." Worked, but uglified the type signature and the
  caller. Replaced with constructor-passed current tool (escape returns
  the same value back). Rule of thumb: if you're about to add a
  sentinel, check whether the caller can supply the "no-op" value
  itself.

---

## 2026-04-25 — Rectangular zone designation + tile inspector

- Added `PlaceZoneRect(x1,y1,x2,y2,kind)` command. `PlaceZone` now
  routes through the same handler as a 1×1 rectangle, so single-tile
  placement and bulk drag share one code path.
- Engine handler normalizes corners, iterates row-major, and skips
  tiles that fail `is_buildable` (water/rock/forest/hill, out of
  bounds, or already occupied). Newly placed buildings are now
  appended to `district.building_ids` — fixes a pre-existing bug where
  player-zoned buildings never got workers assigned by the labor
  system.
- UI flow: with a tool selected, `enter` anchors the first corner and
  highlights it yellow; cursor movement extends a preview rectangle
  with green/red bg colors per tile (will-place vs. will-skip);
  `enter` commits, `escape` cancels. Switching tools or views during
  a drag drops the in-progress rectangle.
- Added `Inspector` widget docked above the Annals log (right column
  is now a `Vertical` of inspector + log). Shows terrain + buildability
  for empty tiles; kind, completion %, workers, district, and farm
  output for buildings.
- Status bar `tool` field now annotates the drag anchor so the player
  knows they're mid-designation.

### Bug surfaced
`_place_zone` (the original single-tile path) never registered new
buildings with their district. Labor system iterates
`district.building_ids` only, so worker assignment silently skipped
every player-zoned building. Fixed in the unified rect handler. If
older saves are loaded and have orphan buildings, they will continue
to be skipped — a one-shot reconciliation pass on load is a future
task.

---

## 2026-04-25 — StatusBar hidden behind Footer

User reported "didn't see time passing." Status bar exists and updates,
but `dock: bottom` on both `StatusBar` and Textual's built-in `Footer`
parked them on the same row (y=29 in an 80×30 pilot); the Footer painted
last and covered the status bar. Removed `dock: bottom` from the
`StatusBar` CSS — now it sits in normal flow above the Footer
(row 28). Time was advancing correctly the whole time (1 tick/sec at
NORMAL); the indicator was just invisible.

Lesson: when adding a docked widget, audit other bottom-docked widgets
in the layout. `Footer` and `Header` are easy to forget because they're
contributed by `App.compose()` boilerplate.

---

## 2026-04-25 — MVP engine bring-up

### What was done
- Locked in tech stack: Python 3.12, Textual (TUI), msgspec (state +
  msgpack save/load), numpy (procgen noise + aggregate math), pytest.
- Project skeleton: `src/spqr/{engine,sim/{models,systems},world/procgen,
  ui/{screens,widgets},persistence}` + `tests/`.
- `GameState` as a single `msgspec.Struct` tree; everything mutable lives
  on it. Off-tree state (live `random.Random`) is reconstructed at load.
- Seeded `random.Random` threaded through every system call. State
  captured into `RngState` on save (getstate/setstate, no fast-forward).
- Tick loop: 1 tick = 1 in-game hour. Speeds: PAUSED/1×/4×/16×/64×.
  UI runs at 20 Hz and accumulates fractional ticks per frame.
- Procgen: fractal-noise heightmap → biomes → carved river → buildable
  site picker → 1–2 barbarian camps → straight-line roads.
- Sim systems (in order): construction, labor, economy
  (production/consumption/tax/upkeep), population (monthly demographics),
  military (daily training), agents (yearly), events (monthly raids).
- Persistence: msgpack via msgspec, atomic write, schema-versioned.
- Textual TUI: city/region map widgets, status bar, "Annals" log
  panel. Hotkeys: `space` pause, `+/-` speed, `r/c` view, arrows pan
  cursor, `1-6` pick zone tool, `enter` place, `s/l` save/load, `q` quit.
- 13 pytest tests covering procgen determinism, save/load round-trip,
  mid-game continuation equality, tick advancement, demographics,
  year-long run, construction completion.

### What worked
- **Hybrid agents + pop pools** — single named magistrate as a `Citizen`,
  rest as `PopPool` aggregates. Cheap to simulate, easy to extend.
- **Deterministic seed → state hash**: same seed yields identical
  SHA-256 across runs. Confirmed in tests and via `--hash-only`.
- **`msgspec.Struct` everywhere** — single typed shape for state plus
  fast msgpack serialization. Save+load round-trip cleanly.
- **Textual pilot harness** — `app.run_test()` lets us drive the TUI
  headlessly (press keys, assert state). Caught two TUI bugs we'd never
  have caught from a static check.
- **Performance budget**: target was 1000 ticks <2 s headless; we hit
  ~6 ms (167k ticks/sec sustained). 100k ticks in <1 s incl. startup.
  Python is fine for this depth of sim — no early Rust port needed.

### What didn't / lessons
- **Float vs int field shape**: `PopPool.slaves: float = 0.0` constructed
  as `slaves=10` (int) encoded as msgpack int, decoded as float (because
  the field is typed float), re-encoded as float. Encode→decode→encode
  wasn't byte-stable. Caught only because the simple round-trip test
  hashed differently. Fix: always construct typed fields with the
  declared type (`slaves=10.0`). Lesson for new structs: be strict at
  construction sites or msgspec will silently coerce on decode.
- **Textual widget IDs must be unique**: gave both `CityMap` and
  `RegionMap` the id `map_holder` to share CSS. Mount error at compose
  time. Fix: distinct ids, use a CSS class for shared styling
  (`.map_holder` not `#map_holder`).
- **Commands queued while paused didn't drain**: original `_apply_pending`
  ran only inside `step()`. While `Speed.PAUSED`, no step → no command
  application → resume command never reached the engine. Fix: hoisted
  `apply_pending()` to a public method and call it every UI frame
  regardless of step count.
- **Starting economy too tight**: city founded in month 1 (January) with
  300 grain — winter losses outpaced production for ~76 days, satisfaction
  crashed before spring. Bumped starting grain to 600. The math was
  correct, but a winter founding date is brutal and the player needs
  runway. Could later randomize the founding date or extend the seasonal
  curve floor. Left "winter is hard" as intentional pressure for now.
- **Magistrate succession unimplemented**: when a magistrate retires/dies,
  no replacement is selected. Logged as out-of-MVP-scope; revisit when
  cursus honorum lands.
- **Region size is fixed at 32×32, city at 60×30**: hard-coded module
  constants. Fine for MVP, but if we ever want size variants this should
  move into a settings struct.

### Decisions to revisit
- Python vs Rust: chose Python first, port-if-needed. Current sim runs at
  140k+ ticks/sec, so the port pressure is low. Trigger to revisit:
  if any single per-tick system takes >100 µs at 1000-pop scale.
- One-district-per-city: simple for MVP. When pop crosses some threshold
  (~500?) the city should split into multiple districts with separate
  pop pools and satisfaction state.
- `Speed` is a 5-step IntEnum. If we want finer control (e.g. 2×, 8×),
  switch to a continuous `ticks_per_sec` float on `GameState`.

---
