from __future__ import annotations

from collections.abc import Iterator

import msgspec

from .building import (
    DEFAULT_LABOR_PRIORITY,
    LUMBER_MILL_ADJACENT_TERRAINS,
    QUARRY_ADJACENT_TERRAINS,
    STORAGE_CAPACITY,
    Building,
    BuildingKind,
)
from .district import District
from .resources import Resources
from .tile import CityTerrain, CityTile


# Terrain types you can build on. Water and rock are off-limits for any
# zone; forest and hill require clearing/leveling work that's out of MVP
# scope. Roads can also lay over plain grass/dirt only.
_BUILDABLE_TERRAIN: frozenset[CityTerrain] = frozenset(
    {CityTerrain.GRASS, CityTerrain.DIRT}
)


class City(msgspec.Struct, frozen=False):
    id: int
    name: str
    # Region tile coords where this city sits.
    region_x: int
    region_y: int
    width: int
    height: int
    # Row-major tilemap; len = width * height.
    tiles: list[CityTile]
    buildings: list[Building] = msgspec.field(default_factory=list)
    next_building_id: int = 0
    districts: list[District] = msgspec.field(default_factory=list)
    treasury: Resources = msgspec.field(default_factory=Resources)
    # Player policy knobs; persisted with the city, mutated through commands.
    tax_rate: float = 0.10
    grain_dole_per_pleb: float = 0.5
    # Worker-allocation order across LaborCategory buckets
    # (CONSTRUCTION, FARMS, LUMBER_MILLS, QUARRIES, WORKSHOPS, OFFICES).
    # Stored as ints, not the enum, to keep encode-byte stability the
    # same as Building.crop / Building.good.
    labor_priority: list[int] = msgspec.field(
        default_factory=lambda: list(DEFAULT_LABOR_PRIORITY)
    )

    def tile(self, x: int, y: int) -> CityTile:
        return self.tiles[y * self.width + x]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_buildable(self, x: int, y: int) -> bool:
        """A tile is buildable if it's in bounds, empty, and on suitable
        terrain (grass / dirt). Used by zone-placement and the build cursor."""
        if not self.in_bounds(x, y):
            return False
        tile = self.tile(x, y)
        if tile.building_id != -1:
            return False
        return tile.terrain in _BUILDABLE_TERRAIN

    def completed_of(self, kind: BuildingKind) -> Iterator[Building]:
        """Yield every completed building of this kind. The single
        idiomatic way to iterate operational buildings of a given type;
        replaces ad-hoc `for b in city.buildings if b.kind == X and
        b.completion >= 1.0` loops scattered across systems."""
        for b in self.buildings:
            if b.kind == kind and b.is_completed:
                yield b

    def total_storage_capacity(self) -> int:
        """Sum of materials storage across all completed storage-bearing
        buildings (forum, warehouses). Caps how much timber + stone the
        city can hold; industry production halts when stocks reach it."""
        cap = 0
        for b in self.buildings:
            if not b.is_completed:
                continue
            cap += STORAGE_CAPACITY.get(b.kind, 0)
        return cap

    def stored_materials(self) -> float:
        """Combined timber + stone currently held in the treasury;
        checked against `total_storage_capacity` by the industry
        system. Per-building local buffers (mill / quarry) are NOT
        counted here — they live outside the warehouse network and
        production overflows into them only when the treasury cap
        is full."""
        return self.treasury.timber + self.treasury.stone

    def available_timber(self) -> float:
        """Total timber the city can spend on construction: treasury
        plus every operational lumber mill's local buffer. Checked by
        `can_afford` and drained by `pay_cost`."""
        total = self.treasury.timber
        for b in self.buildings:
            if b.kind == BuildingKind.LUMBER_MILL and b.is_completed:
                total += b.timber_stored
        return total

    def available_stone(self) -> float:
        """Total stone the city can spend on construction: treasury
        plus every operational quarry's local buffer."""
        total = self.treasury.stone
        for b in self.buildings:
            if b.kind == BuildingKind.QUARRY and b.is_completed:
                total += b.stone_stored
        return total

    def can_afford(self, cost: Resources) -> bool:
        """Like `treasury.can_pay` but considers mill / quarry local
        buffers for timber and stone. Other resources still come
        from the treasury — denarii, grain, vegetables, finished
        goods aren't held outside the central pool."""
        if self.treasury.denarii < cost.denarii:
            return False
        if self.treasury.grain < cost.grain:
            return False
        if self.treasury.vegetables < cost.vegetables:
            return False
        if self.treasury.furniture < cost.furniture:
            return False
        if self.treasury.stoneware < cost.stoneware:
            return False
        if cost.timber > 0 and self.available_timber() < cost.timber:
            return False
        if cost.stone > 0 and self.available_stone() < cost.stone:
            return False
        return True

    def pay_cost(self, cost: Resources) -> None:
        """Drain `cost` from the city. Treasury first; mill / quarry
        local buffers cover any timber / stone shortfall, oldest
        building first (deterministic by `b.id`). Caller is
        responsible for `can_afford` checking — pay_cost will not
        validate, matching `Resources.pay`'s contract."""
        self.treasury.denarii -= cost.denarii
        self.treasury.grain -= cost.grain
        self.treasury.vegetables -= cost.vegetables
        self.treasury.furniture -= cost.furniture
        self.treasury.stoneware -= cost.stoneware
        timber_needed = cost.timber
        stone_needed = cost.stone
        if timber_needed > 0:
            from_treasury = min(timber_needed, self.treasury.timber)
            self.treasury.timber -= from_treasury
            timber_needed -= from_treasury
        if stone_needed > 0:
            from_treasury = min(stone_needed, self.treasury.stone)
            self.treasury.stone -= from_treasury
            stone_needed -= from_treasury
        if timber_needed > 1e-9:
            for b in sorted(
                (
                    b for b in self.buildings
                    if b.kind == BuildingKind.LUMBER_MILL and b.is_completed
                ),
                key=lambda x: x.id,
            ):
                take = min(timber_needed, b.timber_stored)
                if take <= 0:
                    continue
                b.timber_stored -= take
                timber_needed -= take
                if timber_needed <= 1e-9:
                    break
        if stone_needed > 1e-9:
            for b in sorted(
                (
                    b for b in self.buildings
                    if b.kind == BuildingKind.QUARRY and b.is_completed
                ),
                key=lambda x: x.id,
            ):
                take = min(stone_needed, b.stone_stored)
                if take <= 0:
                    continue
                b.stone_stored -= take
                stone_needed -= take
                if stone_needed <= 1e-9:
                    break

    def has_required_adjacency(self, kind: BuildingKind, x: int, y: int) -> bool:
        """Resource-extraction kinds need a matching natural feature on
        an orthogonally-adjacent tile. Lumber mills want a forest
        neighbour; quarries want a hill or rock face. Any other kind
        passes through (no adjacency requirement)."""
        if kind == BuildingKind.LUMBER_MILL:
            wanted = LUMBER_MILL_ADJACENT_TERRAINS
        elif kind == BuildingKind.QUARRY:
            wanted = QUARRY_ADJACENT_TERRAINS
        else:
            return True
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if not self.in_bounds(nx, ny):
                continue
            if self.tile(nx, ny).terrain in wanted:
                return True
        return False
