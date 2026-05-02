from __future__ import annotations

import enum

import msgspec

from .resources import Resources


class BuildingKind(enum.IntEnum):
    EMPTY = 0
    FORUM = 1
    INSULA = 2       # tenement housing
    DOMUS = 3        # patrician housing
    FARM = 4
    GRANARY = 5
    WORKSHOP = 6
    TEMPLE = 7
    ROAD = 8
    WAREHOUSE = 9    # general materials storage


# Capacity in housing units (people housed) by building kind.
HOUSING_CAPACITY: dict[BuildingKind, int] = {
    BuildingKind.INSULA: 40,
    BuildingKind.DOMUS: 8,
}

# Worker slots an *operational* building draws from the labor pool. A farm
# with no workers grows nothing; insulae/domus/temple/road/warehouse
# don't draw operational labor (they're housing or passive infrastructure).
WORKER_SLOTS: dict[BuildingKind, int] = {
    BuildingKind.FARM: 6,
    BuildingKind.WORKSHOP: 4,
    BuildingKind.GRANARY: 2,
    BuildingKind.FORUM: 2,
}

# Builder slots — workers needed to advance construction. A FARM site needs
# 1 builder; a FORUM needs 4. Construction stalls completely with 0 builders.
BUILDER_SLOTS: dict[BuildingKind, int] = {
    BuildingKind.FARM: 1,
    BuildingKind.ROAD: 1,
    BuildingKind.GRANARY: 2,
    BuildingKind.INSULA: 2,
    BuildingKind.WORKSHOP: 2,
    BuildingKind.WAREHOUSE: 2,
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
    BuildingKind.INSULA: 240,
    BuildingKind.WORKSHOP: 240,
    BuildingKind.WAREHOUSE: 300,
    BuildingKind.DOMUS: 360,
    BuildingKind.FORUM: 600,
    BuildingKind.TEMPLE: 720,
}

# Up-front material + denarii cost paid at designation. Player can't
# designate a tile if the city can't pay; partial rectangles place as much
# as the treasury affords.
BUILDING_COST: dict[BuildingKind, Resources] = {
    BuildingKind.ROAD:     Resources(denarii=5,   timber=0,  stone=2,  grain=0),
    BuildingKind.FARM:     Resources(denarii=20,  timber=10, stone=0,  grain=0),
    BuildingKind.GRANARY:  Resources(denarii=40,  timber=15, stone=10, grain=0),
    BuildingKind.INSULA:   Resources(denarii=50,  timber=20, stone=10, grain=0),
    BuildingKind.WORKSHOP: Resources(denarii=60,  timber=15, stone=10, grain=0),
    BuildingKind.WAREHOUSE:Resources(denarii=80,  timber=20, stone=20, grain=0),
    BuildingKind.DOMUS:    Resources(denarii=100, timber=20, stone=30, grain=0),
    BuildingKind.TEMPLE:   Resources(denarii=150, timber=20, stone=40, grain=0),
    BuildingKind.FORUM:    Resources(denarii=200, timber=30, stone=50, grain=0),
}

# Materials storage capacity (timber + stone share one pool). The total
# city storage is the sum across all completed storage-bearing buildings;
# excess additions are refused (in MVP, materials are only consumed not
# produced, so the cap doesn't bite during play yet).
STORAGE_CAPACITY: dict[BuildingKind, int] = {
    BuildingKind.FORUM: 100,      # mayor's office stockpile
    BuildingKind.WAREHOUSE: 250,  # general storage
}


# Grain mechanics ------------------------------------------------------------

# Growing season covers months 3..9 (March through September) inclusive.
# Outside this window, farms tick maturity nowhere even with full crew.
GROWING_SEASON_MONTHS: frozenset[int] = frozenset({3, 4, 5, 6, 7, 8, 9})

# Worker-hours required to bring one farm from maturity 0.0 -> 1.0.
# With 6 workers (the FARM operational worker-slot count), that's 480
# hours = 20 game days; a farm fits ~10 harvests into a 7-month growing
# season, comfortably outproducing aggregate consumption.
FARM_WORKER_HOURS_PER_HARVEST: int = 2880

# Yield deposited into farm.grain_stored when maturity hits 1.0.
GRAIN_YIELD_PER_HARVEST: float = 600.0

# Maximum grain stored on a farm awaiting transport. If full, growth still
# proceeds but the farm can't take more harvests until storage drops.
FARM_GRAIN_CAPACITY: float = 1200.0

# Granary inventory cap. Sized so the starter stockpile (~2500 grain to
# survive the founding winter) fits in a single granary; late-game cities
# still want multiple granaries for spatial reach, not just capacity.
GRANARY_CAPACITY: float = 3000.0

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
    0: BuildingKind.INSULA,   # PLEB
    1: BuildingKind.DOMUS,    # PATRICIAN
}


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
    # Grain physically held: harvest sitting on a farm awaiting pickup,
    # or stockpile in a granary.
    grain_stored: float = 0.0
    # Per-tick inventory snapshots, only used by granaries. Bounded to
    # GRANARY_HISTORY_MAX_SAMPLES; older samples are discarded as new
    # ones arrive. Used by the inspector "Info → graph" view.
    inventory_history: list[float] = msgspec.field(default_factory=list)
