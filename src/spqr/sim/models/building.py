from __future__ import annotations

import enum

import msgspec

from .resources import Resources


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
    BuildingKind.FARM:        Resources(denarii=20,  timber=10, stone=0,  grain=0),
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

# Materials storage capacity (timber + stone share one pool). The total
# city storage is the sum across all completed storage-bearing buildings;
# excess additions are refused (in MVP, materials are only consumed not
# produced, so the cap doesn't bite during play yet).
STORAGE_CAPACITY: dict[BuildingKind, int] = {
    BuildingKind.FORUM: 100,      # mayor's office stockpile
    BuildingKind.WAREHOUSE: 250,  # general storage
}


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
    int(Crop.WHEAT): 150.0,
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

# Per-warehouse vegetables cap. Vegetables are the supplement, not the
# staple, so a warehouse holds less than a granary. Materials storage
# (timber + stone) is tracked separately via STORAGE_CAPACITY and shares
# no pool with vegetables.
WAREHOUSE_VEGETABLES_CAPACITY: float = 1000.0

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
# patricians 0.050/h).

# Indexes match PopClass IntEnum values (PLEB=0, PATRICIAN=1).
MEAL_INTERVAL_HOURS: dict[int, int] = {
    0: 24,   # PLEB: once a day
    1: 12,   # PATRICIAN: twice a day
}

# Offset within the period — staggers the daily rhythm.
MEAL_OFFSET_HOURS: dict[int, int] = {
    0: 6,    # plebs 6am daily
    1: 9,    # patricians 9am, 9pm
}

GRAIN_PER_MEAL: dict[int, float] = {
    0: 0.48,  # pleb: 0.48 every 24h = 0.020/h
    1: 0.60,  # patrician: 0.60 every 12h = 0.050/h
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
    0: 3,    # undeveloped land — squatter family
    1: 6,    # huts (timber)
    2: 15,   # cottages (timber + stone)
    3: 40,   # insula — multi-story tenement (timber + stone)
}
RESIDENCE_TIER_NAME: dict[int, str] = {
    0: "undeveloped",
    1: "huts",
    2: "cottages",
    3: "insula",
}
RESIDENCE_TIER_UPGRADE_TIMBER_COST: dict[int, int] = {
    1: 5,    # huts go up cheaply
    2: 20,   # cottages
    3: 50,   # insula
}
RESIDENCE_TIER_UPGRADE_STONE_COST: dict[int, int] = {
    1: 0,    # huts: no stone
    2: 10,   # cottages: light masonry
    3: 25,   # insula: heavy masonry
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

# Industrial nuisance. Residences within INDUSTRIAL_NUISANCE_RADIUS
# (Chebyshev) of any completed quarry or lumber mill suffer two
# effects: (a) tier capped at huts (cottages and insulae are unwilling
# to put up with the smoke and noise), (b) a monthly satisfaction
# penalty proportional to the fraction of district residences in the
# nuisance zone. Mirrors the road-desirability mechanic but inverted.
INDUSTRIAL_NUISANCE_RADIUS: int = 4
INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH: float = 0.04


# Industry — material production buildings. Lumber mills produce timber,
# quarries produce stone. Both halt when total city materials
# (treasury.timber + treasury.stone) hit total_storage_capacity, which
# scales with forum + warehouse count: this is what the user's
# "yields are stored in warehouse" rule means in practice.
LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK: float = 0.05
QUARRY_STONE_PER_WORKER_PER_TICK: float = 0.04

# Workshop tuning. Each worker tick consumes INPUT of the goods'
# raw material (timber for furniture, stone for stoneware) from the
# city treasury and produces OUTPUT of the finished good. Production
# halts entirely when the input pool is empty — no partial yields.
# Output rate is slightly less than input rate, representing waste.
WORKSHOP_INPUT_PER_WORKER_PER_TICK: float = 0.03
WORKSHOP_OUTPUT_PER_WORKER_PER_TICK: float = 0.02


def hours_until_next_meal(tick: int, cls: int) -> int:
    """Hours from `tick` until class `cls`'s next meal event. Returns 0 if
    a meal fires on this exact tick."""
    interval = MEAL_INTERVAL_HOURS[cls]
    offset = MEAL_OFFSET_HOURS[cls]
    elapsed = (tick - offset) % interval
    return 0 if elapsed == 0 else interval - elapsed


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
