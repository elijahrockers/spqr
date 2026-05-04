from __future__ import annotations

import enum

import msgspec

from .resources import Resources
from .tile import CityTerrain


class BuildingKind(enum.IntEnum):
    EMPTY = 0
    FORUM = 1
    RESIDENCE = 2        # pleb residence; tier carries the actual class
    DOMUS = 3            # patrician housing
    FARM = 4
    GRANARY = 5
    WORKSHOP = 6
    TEMPLE = 7
    ROAD = 8
    WAREHOUSE = 9        # general materials storage
    LUMBER_MILL = 10     # produces timber from forest tiles
    QUARRY = 11          # produces stone from rock tiles
    OFFICE = 12          # admin reach + tax collection; gates cottages


class Crop(enum.IntEnum):
    """What a farm is growing. Wheat is the staple grain; vegetables are
    a placeholder slot — buildable and switchable but no consumer yet."""
    WHEAT = 0
    VEGETABLES = 1


class Good(enum.IntEnum):
    """What a workshop is producing. Furniture consumes timber;
    stoneware consumes stone. Both produce into the treasury as
    aggregate stockpiles. Future iterations will add consumers (e.g.
    domus demand for furniture, civic projects for stoneware)."""
    FURNITURE = 0
    STONEWARE = 1


class LaborCategory(enum.IntEnum):
    """Worker-allocation buckets for the per-city labor priority list.
    Construction is a state, not a kind — any building under
    construction lands in CONSTRUCTION regardless of its eventual
    kind. The other categories map 1:1 to BuildingKind values that
    take operational workers. Storage / civic / housing kinds have no
    bucket; `labor_category_for` returns None for them."""
    CONSTRUCTION = 0
    FARMS        = 1
    LUMBER_MILLS = 2
    QUARRIES     = 3
    WORKSHOPS    = 4
    OFFICES      = 5


# Default priority order — Construction first (so new buildings finish
# instead of stalling), then food production, raw materials, finished
# goods, and finally civic admin. Stored as ints (not the enum) on
# `City.labor_priority` to match the encode-byte stability rule that
# `Building.crop` / `Building.good` already follow.
DEFAULT_LABOR_PRIORITY: list[int] = [
    int(LaborCategory.CONSTRUCTION),
    int(LaborCategory.FARMS),
    int(LaborCategory.LUMBER_MILLS),
    int(LaborCategory.QUARRIES),
    int(LaborCategory.WORKSHOPS),
    int(LaborCategory.OFFICES),
]


_KIND_TO_LABOR_CATEGORY: dict[BuildingKind, LaborCategory] = {
    BuildingKind.FARM:        LaborCategory.FARMS,
    BuildingKind.LUMBER_MILL: LaborCategory.LUMBER_MILLS,
    BuildingKind.QUARRY:      LaborCategory.QUARRIES,
    BuildingKind.WORKSHOP:    LaborCategory.WORKSHOPS,
    BuildingKind.OFFICE:      LaborCategory.OFFICES,
}


# Capacity in housing units (people housed) by building kind. RESIDENCE is
# tier-driven (use RESIDENCE_TIER_CAPACITY); DOMUS is a single tier for now.
HOUSING_CAPACITY: dict[BuildingKind, int] = {
    BuildingKind.DOMUS: 8,
}

# Operational worker slots by building kind (NOT including FARM — farms
# are crop-driven, look up via farm_worker_slots()). A wheat farm needs
# 1 worker per harvest; a vegetables farm needs more hands for less time.
WORKER_SLOTS: dict[BuildingKind, int] = {
    BuildingKind.WORKSHOP: 4,
    BuildingKind.GRANARY: 2,
    BuildingKind.FORUM: 2,
    BuildingKind.LUMBER_MILL: 2,
    BuildingKind.QUARRY: 2,
    BuildingKind.OFFICE: 3,
}

# Builder slots — workers needed to advance construction. A FARM site needs
# 1 builder; a FORUM needs 4. Construction stalls completely with 0 builders.
BUILDER_SLOTS: dict[BuildingKind, int] = {
    BuildingKind.FARM: 1,
    BuildingKind.ROAD: 1,
    BuildingKind.GRANARY: 2,
    BuildingKind.RESIDENCE: 2,
    BuildingKind.WORKSHOP: 2,
    BuildingKind.WAREHOUSE: 2,
    BuildingKind.LUMBER_MILL: 2,
    BuildingKind.QUARRY: 2,
    BuildingKind.OFFICE: 2,
    BuildingKind.DOMUS: 3,
    BuildingKind.FORUM: 4,
    BuildingKind.TEMPLE: 4,
}

# Total builder-hours to complete a building. Wall-clock time = BUILD_HOURS /
# builders_assigned. With full builder allocation, smaller civic builds
# finish in ~1 game week, larger civic projects in ~3-5 weeks.
BUILD_HOURS: dict[BuildingKind, int] = {
    BuildingKind.ROAD: 24,
    BuildingKind.FARM: 168,
    BuildingKind.GRANARY: 200,
    BuildingKind.LUMBER_MILL: 200,
    BuildingKind.RESIDENCE: 240,
    BuildingKind.WORKSHOP: 240,
    BuildingKind.QUARRY: 240,
    BuildingKind.OFFICE: 240,
    BuildingKind.WAREHOUSE: 300,
    BuildingKind.DOMUS: 360,
    BuildingKind.FORUM: 600,
    BuildingKind.TEMPLE: 720,
}

# Up-front material + denarii cost paid at designation. Player can't
# designate a tile if the city can't pay; partial rectangles place as much
# as the treasury affords.
BUILDING_COST: dict[BuildingKind, Resources] = {
    BuildingKind.ROAD:        Resources(denarii=5,   timber=0,  stone=2,  grain=0),
    BuildingKind.FARM:        Resources(denarii=20,  timber=0, stone=0,  grain=0),
    BuildingKind.GRANARY:     Resources(denarii=40,  timber=15, stone=10, grain=0),
    BuildingKind.RESIDENCE:   Resources(denarii=50,  timber=0,  stone=0,  grain=0),
    BuildingKind.WORKSHOP:    Resources(denarii=60,  timber=15, stone=10, grain=0),
    BuildingKind.LUMBER_MILL: Resources(denarii=80,  timber=0,  stone=10, grain=0),
    BuildingKind.WAREHOUSE:   Resources(denarii=80,  timber=20, stone=0,  grain=0),
    BuildingKind.OFFICE:      Resources(denarii=80,  timber=10, stone=10, grain=0),
    BuildingKind.DOMUS:       Resources(denarii=100, timber=20, stone=30, grain=0),
    BuildingKind.QUARRY:      Resources(denarii=100, timber=20, stone=0,  grain=0),
    BuildingKind.TEMPLE:      Resources(denarii=150, timber=20, stone=40, grain=0),
    BuildingKind.FORUM:       Resources(denarii=200, timber=30, stone=50, grain=0),
}

# Per-warehouse total capacity, distributed across the five storable
# goods (timber, stone, vegetables, furniture, stoneware) by the
# player-configurable `warehouse_cap_*` fields on each Building.
# Default is uniform — see WAREHOUSE_DEFAULT_CAP_* below. The split is
# what gets configured; the total is fixed.
WAREHOUSE_TOTAL_CAPACITY: int = 300

# Default per-good split for a freshly-designated warehouse. Must sum
# to WAREHOUSE_TOTAL_CAPACITY (60 × 5 = 300).
WAREHOUSE_DEFAULT_CAP_TIMBER: int = 60
WAREHOUSE_DEFAULT_CAP_STONE: int = 60
WAREHOUSE_DEFAULT_CAP_VEGETABLES: int = 60
WAREHOUSE_DEFAULT_CAP_FURNITURE: int = 60
WAREHOUSE_DEFAULT_CAP_STONEWARE: int = 60

# Forum contributes a fixed split to the city's per-material caps.
# Forum doesn't store vegetables or finished goods — it's a civic
# building, not a warehouse.
FORUM_TIMBER_CAPACITY: int = 50
FORUM_STONE_CAPACITY: int = 50


# Crop / farm mechanics ------------------------------------------------------

# Growing season covers months 3..9 (March through September) inclusive.
# Outside this window, farms tick maturity nowhere even with full crew.
GROWING_SEASON_MONTHS: frozenset[int] = frozenset({3, 4, 5, 6, 7, 8, 9})

# Per-crop tuning. Both crops cap at 3 workers; harvest frequency
# scales linearly with workers via grain.py's maturity advance
# (`workers / hours_per_harvest`). Yield per harvest is fixed — more
# workers means more cycles per year, not bigger harvests. With 1
# worker a wheat farm matches the original "1 harvest/month" pace and
# sustains one tier-1 hut; with 3 workers it harvests 3× faster and
# can sustain a small cottage or a few huts.
CROP_WORKER_SLOTS: dict[int, int] = {
    int(Crop.WHEAT): 3,
    int(Crop.VEGETABLES): 3,
}
CROP_WORKER_HOURS_PER_HARVEST: dict[int, int] = {
    int(Crop.WHEAT): 720,         # 1 worker × 720 = 1 harvest/month; 3 workers ≈ 10 days
    int(Crop.VEGETABLES): 480,    # 3 workers × 160 ≈ 1 harvest/week
}
CROP_YIELD_PER_HARVEST: dict[int, float] = {
    int(Crop.WHEAT): 100.0,
    int(Crop.VEGETABLES): 80.0,
}


_DEFAULT_CROP_WORKER_HOURS_PER_HARVEST = 720
_DEFAULT_CROP_YIELD_PER_HARVEST = 100.0


# Maximum grain stored on a farm awaiting transport. If full, growth still
# proceeds but the farm can't take more harvests until storage drops.
FARM_GRAIN_CAPACITY: float = 1200.0

# Granary inventory cap. Sized so a small early city can stockpile a
# season's worth; late-game cities still want multiple granaries for
# spatial reach, not just capacity.
GRANARY_CAPACITY: float = 3000.0

# Per-warehouse vegetables cap is now `Building.warehouse_cap_vegetables`
# — set per warehouse, defaults to WAREHOUSE_DEFAULT_CAP_VEGETABLES.
# The old single global constant has been replaced so a player can
# dedicate one warehouse to food and another to materials.

# Maximum hourly samples retained in `Building.inventory_history` per
# granary. 720 = 30 game days; supports both an hourly view of the last
# couple of days and a 30-day daily-aggregate view from the same buffer.
GRANARY_HISTORY_MAX_SAMPLES: int = 720

# Grain transferred per tick from a farm to its target granary.
GRAIN_TRANSPORT_RATE: float = 8.0

# Spatial reach. Dijkstra over the city tilemap; road tiles cost 1.0 to
# enter, plain tiles 2.5, building tiles 2.0, water/rock are impassable.
# Total cost <= GRANARY_REACH_COST means "in range." Without roads,
# this works out to ~5 Manhattan tiles; with a road network, ~12.
GRANARY_REACH_COST: float = 12.0
FARM_TRANSPORT_REACH_COST: float = 16.0

# Office reach scales linearly with assigned workers. With 1 worker the
# reach is 6 (a small neighborhood); with 3 workers it's 18 (a full
# district). Used by housing (cottage tier gate) and economy (taxation).
# The same Dijkstra primitive backs the reach as granaries — roads
# extend it, water/rock blocks it.
OFFICE_REACH_PER_WORKER: float = 6.0

# Offices occupy a 2×2 footprint. Placement requires all four tiles
# (anchor, anchor+x, anchor+y, anchor+xy) to be buildable; cost is
# paid once. All four tile.building_ids point to the same office
# building, so the inspector resolves to the same struct from any
# corner — no special "find the anchor" logic in the UI.
OFFICE_FOOTPRINT_W: int = 2
OFFICE_FOOTPRINT_H: int = 2


# Demolition tools.
# Undesignate is free: it cancels an in-progress designation and
# refunds 100% of the BUILDING_COST. Only applies to buildings still
# under construction (b.is_under_construction).
# Bulldoze is the after-the-fact demolisher: costs BULLDOZE_DENARII_COST
# per building (paid once even for multi-tile structures like office),
# refunds BULLDOZE_REFUND_FRACTION of the original timber+stone cost.
# Denarii are NOT refunded — they're considered sunk into operations.
BULLDOZE_DENARII_COST: float = 10.0
BULLDOZE_REFUND_FRACTION: float = 0.5


# Per-class meal mechanics. Meals are discrete events scheduled by tick:
# class C eats when `(tick - MEAL_OFFSET_HOURS[C]) % MEAL_INTERVAL_HOURS[C]
# == 0`. Per-meal grain is calibrated so the daily total per individual
# matches the original continuous hourly rates (plebs 0.020/h,
# patricians 0.050/h). All classes eat once a day at 6am — keeps the
# simulation legible (one meal "tick" per day across the city) without
# changing per-class consumption volumes.

# Indexes match PopClass IntEnum values (PLEB=0, PATRICIAN=1).
MEAL_INTERVAL_HOURS: dict[int, int] = {
    0: 24,   # PLEB: once a day
    1: 24,   # PATRICIAN: once a day
}

# Offset within the period — staggers the daily rhythm. Both classes
# share 6am so granary inventories drop in single, easy-to-read steps.
MEAL_OFFSET_HOURS: dict[int, int] = {
    0: 6,
    1: 6,
}

GRAIN_PER_MEAL: dict[int, float] = {
    0: 0.48,  # pleb: 0.48 every 24h = 0.020/h
    1: 1.20,  # patrician: 1.20 every 24h = 0.050/h
}

# Each civilian class is housed in exactly one BuildingKind.
CLASS_HOUSING: dict[int, "BuildingKind"] = {
    0: BuildingKind.RESIDENCE,    # PLEB
    1: BuildingKind.DOMUS,    # PATRICIAN
}


# Residence tier system. Designation drops a tier-0 plot ("undeveloped
# land") with no construction time. As long as a road sits within
# RESIDENCE_AMENITY_REACH_COST tiles and the city has the required
# materials, the housing system advances tier monthly. Higher tiers
# demand stone alongside timber.
RESIDENCE_MAX_TIER: int = 3
RESIDENCE_TIER_CAPACITY: dict[int, int] = {
    0: 2,    # undeveloped land — squatter family
    1: 4,    # huts (timber)
    2: 8,   # cottages (timber + stone)
    3: 16,   # insula — multi-story tenement (timber + stone)
}
RESIDENCE_TIER_NAME: dict[int, str] = {
    0: "undeveloped",
    1: "huts",
    2: "cottages",
    3: "insula",
}
RESIDENCE_TIER_UPGRADE_TIMBER_COST: dict[int, int] = {
    1: 10,    # huts go up cheaply
    2: 20,   # cottages
    3: 50,   # insula
}
RESIDENCE_TIER_UPGRADE_STONE_COST: dict[int, int] = {
    1: 0,    # huts: no stone
    2: 10,   # cottages: light masonry
    3: 25,   # insula: heavy masonry
}
# Furniture / stoneware are workshop output; tiers 2+ pull on them so
# the player has a reason to stand up workshops + extra warehouses
# before densifying. Tier 1 huts stay quick & dirty (no finished goods).
RESIDENCE_TIER_UPGRADE_FURNITURE_COST: dict[int, int] = {
    1: 0,
    2: 50,    # cottages: a tenant family's furnishings
    3: 100,   # insula: many doors, many tables
}
RESIDENCE_TIER_UPGRADE_STONEWARE_COST: dict[int, int] = {
    1: 0,
    2: 0,
    3: 50,    # insula: amphorae, fired tile, pots
}
# Dijkstra reach (over the same cost model used by spatial.coverage) within
# which a residence must find a ROAD building to qualify for tier upgrades.
RESIDENCE_AMENITY_REACH_COST: float = 4.0

# Road desirability buff. A residence with a completed road within
# Chebyshev distance ROAD_DESIRABILITY_RADIUS contributes a per-month
# satisfaction bonus to its district. Computed as the fraction of
# residences with road access × ROAD_DESIRABILITY_BONUS_PER_MONTH, so a
# fully-roaded district gets the full bonus and a partly-roaded one gets
# proportionally less. Distinct from RESIDENCE_AMENITY_REACH_COST (which
# is a Dijkstra cost cap that gates tier upgrades): this is a tile-radius
# proximity check that nudges happiness everywhere in the district.
ROAD_DESIRABILITY_RADIUS: int = 2
ROAD_DESIRABILITY_BONUS_PER_MONTH: float = 0.02

# Industrial nuisance. Residences within the per-kind nuisance radius
# (Chebyshev) of any completed industrial building suffer two effects:
# (a) tier capped at huts (cottages and insulae are unwilling to put
# up with the smoke and noise), (b) a monthly satisfaction penalty
# proportional to the fraction of district residences in the nuisance
# zone. Mirrors the road-desirability mechanic but inverted.
#
# Per-kind radii: mills + quarries carry farther than workshops because
# they're heavier industry. Lookup goes through `nuisance_radius_for`.
INDUSTRIAL_NUISANCE_RADIUS: int = 5      # default for mill / quarry
WORKSHOP_NUISANCE_RADIUS: int = 3
NUISANCE_RADIUS_BY_KIND: dict[BuildingKind, int] = {
    BuildingKind.LUMBER_MILL: INDUSTRIAL_NUISANCE_RADIUS,
    BuildingKind.QUARRY:      INDUSTRIAL_NUISANCE_RADIUS,
    BuildingKind.WORKSHOP:    WORKSHOP_NUISANCE_RADIUS,
}
INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH: float = 0.04


def nuisance_radius_for(kind: BuildingKind) -> int:
    """Per-kind nuisance radius. 0 for kinds that don't emit nuisance —
    callers can treat 0 as 'no zone' without an explicit membership
    check."""
    return NUISANCE_RADIUS_BY_KIND.get(kind, 0)


# Industry — material production buildings. Lumber mills produce timber,
# quarries produce stone. Production lands first in the city treasury
# (capped by total_storage_capacity from forum + warehouses); when the
# treasury is full, output spills into the producing building's local
# buffer up to LUMBER_MILL_TIMBER_BUFFER / QUARRY_STONE_BUFFER. The
# buffer keeps an early-game city building when no warehouse exists
# yet — construction can still pay from it via City.pay_cost. Both
# pools halt production once the treasury and the local buffer are
# full.
LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK: float = 0.05
QUARRY_STONE_PER_WORKER_PER_TICK: float = 0.04
LUMBER_MILL_TIMBER_BUFFER: float = 50.0
QUARRY_STONE_BUFFER: float = 50.0


# Adjacency rules for resource-extraction buildings. A lumber mill
# only goes up next to forest (workers fell trees on adjacent tiles);
# a quarry only goes up next to a hill or rock face. Adjacency is
# 4-directional (Manhattan radius 1) — diagonal-only contact would
# stretch the visual link. Checked at placement time only; if the
# adjacent forest is later cut down, the mill keeps producing on
# pretend-forest, same as a real-world land-use grandfather clause.
LUMBER_MILL_ADJACENT_TERRAINS: frozenset[CityTerrain] = frozenset(
    {CityTerrain.FOREST}
)
QUARRY_ADJACENT_TERRAINS: frozenset[CityTerrain] = frozenset(
    {CityTerrain.HILL, CityTerrain.ROCK}
)

# Workshop tuning. Each worker tick consumes INPUT of the goods'
# raw material (timber for furniture, stone for stoneware) from the
# city treasury and produces OUTPUT of the finished good. Production
# halts entirely when the input pool is empty — no partial yields.
# Output rate is slightly less than input rate, representing waste.
WORKSHOP_INPUT_PER_WORKER_PER_TICK: float = 0.03
WORKSHOP_OUTPUT_PER_WORKER_PER_TICK: float = 0.02

# Local on-workshop buffer for finished goods. Output lands in the
# city treasury first (capped by warehouse furniture/stoneware caps);
# the spillover lands in this buffer up to WORKSHOP_OUTPUT_BUFFER per
# workshop. Production halts when both treasury and the local buffer
# are full. Mirrors LUMBER_MILL_TIMBER_BUFFER for mills.
WORKSHOP_OUTPUT_BUFFER: float = 50.0


def hours_until_next_meal(tick: int, cls: int) -> int:
    """Hours from `tick` until class `cls`'s next meal event. Returns 0 if
    a meal fires on this exact tick."""
    interval = MEAL_INTERVAL_HOURS[cls]
    offset = MEAL_OFFSET_HOURS[cls]
    elapsed = (tick - offset) % interval
    return 0 if elapsed == 0 else interval - elapsed


def labor_category_for(b: "Building") -> LaborCategory | None:
    """Bucket a building belongs to for labor priority allocation.
    Construction wins over kind: an under-construction quarry sits in
    CONSTRUCTION, not QUARRIES. Returns None for kinds that take no
    workers (residences, granaries, warehouses, roads, forum, temple,
    domus) so the caller knows to zero `workers_assigned` without
    spending pool capacity."""
    if b.is_under_construction:
        return LaborCategory.CONSTRUCTION
    return _KIND_TO_LABOR_CATEGORY.get(b.kind)


class Building(msgspec.Struct, frozen=False):
    id: int
    kind: BuildingKind
    x: int
    y: int
    workers_assigned: int = 0
    # Construction progress 0.0 .. 1.0; 1.0 = operational. While < 1.0,
    # workers_assigned counts builders rather than operators.
    completion: float = 1.0
    # Grain growth on a farm; meaningless on other kinds. 0.0 = freshly
    # sown, 1.0 = ripe and harvested (resets back to 0 when reaped).
    grain_maturity: float = 0.0
    # Grain physically held: harvest sitting on a wheat farm awaiting
    # pickup, or stockpile in a granary.
    grain_stored: float = 0.0
    # Vegetables physically held: harvest sitting on a vegetables farm
    # awaiting pickup, or stockpile in a warehouse.
    vegetables_stored: float = 0.0
    # Local timber buffer on a lumber mill (cap LUMBER_MILL_TIMBER_BUFFER).
    # Industry production spills here when the city treasury is at the
    # storage cap; construction can pay from it via City.pay_cost.
    # Meaningless on other building kinds.
    timber_stored: float = 0.0
    # Local stone buffer on a quarry (cap QUARRY_STONE_BUFFER). Same
    # spillover-then-pay-from-it dynamic as timber_stored on the mill.
    stone_stored: float = 0.0
    # Local furniture / stoneware buffers on a workshop. The workshop
    # produces into the central treasury first (capped by warehouses);
    # when the treasury cap is hit, output spills into whichever of
    # these matches the workshop's `good`, up to WORKSHOP_OUTPUT_BUFFER.
    # Production halts only when treasury and the local buffer are
    # both full.
    furniture_stored: float = 0.0
    stoneware_stored: float = 0.0
    # House upgrade tier (0..RESIDENCE_MAX_TIER). Meaningless on other kinds.
    tier: int = 0
    # Player-set tier ceiling for RESIDENCE buildings. The housing system
    # stops upgrading once `tier == tier_cap`. Default = RESIDENCE_MAX_TIER
    # (3) means "no cap, upgrade as far as the city can support."
    # Meaningless on other building kinds. The cap can be lowered to
    # freeze a residence at huts or cottages even when materials and
    # roads would otherwise advance it; useful for keeping a low-density
    # neighborhood from densifying into insulae.
    tier_cap: int = 3
    # Crop sown on a farm (Crop IntEnum value). Meaningless on other kinds.
    crop: int = 0
    # Good produced by a workshop (Good IntEnum value: 0=furniture,
    # 1=stoneware). Meaningless on other kinds. Workshop consumes the
    # corresponding raw material from treasury per worker per tick.
    good: int = 0
    # Per-tick inventory snapshots, only used by granaries. Bounded to
    # GRANARY_HISTORY_MAX_SAMPLES; older samples are discarded as new
    # ones arrive. Used by the inspector "Info → graph" view.
    inventory_history: list[float] = msgspec.field(default_factory=list)
    # Player-configurable per-good capacity split for a WAREHOUSE,
    # summing to <= WAREHOUSE_TOTAL_CAPACITY. Each warehouse contributes
    # its `warehouse_cap_*` to the corresponding city-wide cap (industry
    # halts when the treasury reaches the per-material total). The
    # vegetables cap is the per-warehouse vegetables limit used by
    # grain transport — not pooled across warehouses. Meaningless on
    # non-WAREHOUSE kinds; the defaults match the uniform-distribution
    # starter for a new warehouse (60 × 5 = 300).
    warehouse_cap_timber: int = 60
    warehouse_cap_stone: int = 60
    warehouse_cap_vegetables: int = 60
    warehouse_cap_furniture: int = 60
    warehouse_cap_stoneware: int = 60

    # --- state predicates -------------------------------------------------

    @property
    def is_completed(self) -> bool:
        """True when the building is operational. The single check —
        scattered `b.completion >= 1.0` comparisons are the same shape
        of bug as reimplementing spatial.coverage in a UI helper."""
        return self.completion >= 1.0

    @property
    def is_under_construction(self) -> bool:
        return self.completion < 1.0

    # --- housing ----------------------------------------------------------

    def residence_capacity(self) -> int:
        """Tier-aware housing capacity. The single source of truth —
        every consumer (grain meal demand, migration cap, inspector
        display) must go through this method, otherwise tier-aware
        capacity drifts silently between systems."""
        if self.kind == BuildingKind.RESIDENCE:
            return RESIDENCE_TIER_CAPACITY.get(self.tier, 0)
        return HOUSING_CAPACITY.get(self.kind, 0)

    # --- labor ------------------------------------------------------------

    def operational_worker_slots(self) -> int:
        """Worker slots an operational building needs. Farms are
        crop-driven (wheat: 1, vegetables: 4); other kinds use the
        WORKER_SLOTS constant. Single source of truth — labor and
        inspector both route through it so a wheat farm correctly
        draws 1."""
        if self.kind == BuildingKind.FARM:
            return self.farm_worker_slots()
        return WORKER_SLOTS.get(self.kind, 0)

    # --- farming ----------------------------------------------------------

    def farm_worker_slots(self) -> int:
        return CROP_WORKER_SLOTS.get(int(self.crop), 1)

    def farm_worker_hours_per_harvest(self) -> int:
        return CROP_WORKER_HOURS_PER_HARVEST.get(
            int(self.crop), _DEFAULT_CROP_WORKER_HOURS_PER_HARVEST
        )

    def farm_yield_per_harvest(self) -> float:
        return CROP_YIELD_PER_HARVEST.get(
            int(self.crop), _DEFAULT_CROP_YIELD_PER_HARVEST
        )
