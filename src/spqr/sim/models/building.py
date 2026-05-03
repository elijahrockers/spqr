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


class Crop(enum.IntEnum):
    """What a farm is growing. Wheat is the staple grain; vegetables are
    a placeholder slot — buildable and switchable but no consumer yet."""
    WHEAT = 0
    VEGETABLES = 1


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
    BuildingKind.WAREHOUSE:   Resources(denarii=80,  timber=20, stone=20, grain=0),
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

# Per-crop tuning. Wheat is the staple: 1 worker, monthly harvest cycle
# (1 worker × 720h = 720 worker-hours), yield calibrated so a single
# wheat farm sustains one tier-1 (huts, 6 plebs) house year-round even
# accounting for the 7-month growing season — 7 × 150 = 1050 grain/year
# vs. 6 × 0.48 × 365 ≈ 1051 grain/year demand.
CROP_WORKER_SLOTS: dict[int, int] = {
    int(Crop.WHEAT): 1,
    int(Crop.VEGETABLES): 4,
}
CROP_WORKER_HOURS_PER_HARVEST: dict[int, int] = {
    int(Crop.WHEAT): 720,         # 1 worker × 720 = 1 harvest/month
    int(Crop.VEGETABLES): 480,    # 4 workers × 120 = 1 harvest per ~5 days
}
CROP_YIELD_PER_HARVEST: dict[int, float] = {
    int(Crop.WHEAT): 150.0,
    int(Crop.VEGETABLES): 80.0,
}


def farm_worker_slots(b: "Building") -> int:
    return CROP_WORKER_SLOTS.get(int(b.crop), 1)


def farm_worker_hours_per_harvest(b: "Building") -> int:
    return CROP_WORKER_HOURS_PER_HARVEST.get(int(b.crop), 720)


def farm_yield_per_harvest(b: "Building") -> float:
    return CROP_YIELD_PER_HARVEST.get(int(b.crop), 100.0)


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


# Industry — material production buildings. Lumber mills produce timber,
# quarries produce stone. Both halt when total city materials
# (treasury.timber + treasury.stone) hit total_storage_capacity, which
# scales with forum + warehouse count: this is what the user's
# "yields are stored in warehouse" rule means in practice.
LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK: float = 0.05
QUARRY_STONE_PER_WORKER_PER_TICK: float = 0.04


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
    # Crop sown on a farm (Crop IntEnum value). Meaningless on other kinds.
    crop: int = 0
    # Per-tick inventory snapshots, only used by granaries. Bounded to
    # GRANARY_HISTORY_MAX_SAMPLES; older samples are discarded as new
    # ones arrive. Used by the inspector "Info → graph" view.
    inventory_history: list[float] = msgspec.field(default_factory=list)


def residence_capacity(b: Building) -> int:
    """Tier-aware housing capacity. The single source of truth — every
    consumer (grain meal demand, migration cap, inspector display) must
    go through this helper, otherwise tier-aware capacity drifts silently
    between systems."""
    if b.kind == BuildingKind.RESIDENCE:
        return RESIDENCE_TIER_CAPACITY.get(b.tier, 0)
    return HOUSING_CAPACITY.get(b.kind, 0)


def operational_worker_slots(b: Building) -> int:
    """Worker slots an operational building needs. Farms are crop-driven
    (wheat: 1, vegetables: 4); other kinds use the WORKER_SLOTS constant.
    Like residence_capacity, this is the single source of truth — labor and
    inspector both route through it so a wheat farm correctly draws 1."""
    if b.kind == BuildingKind.FARM:
        return farm_worker_slots(b)
    return WORKER_SLOTS.get(b.kind, 0)
