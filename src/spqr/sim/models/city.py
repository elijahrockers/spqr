from __future__ import annotations

from collections.abc import Iterator

import msgspec

from .building import STORAGE_CAPACITY, Building, BuildingKind
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
        """Combined timber + stone currently held; checked against
        `total_storage_capacity` by the industry system."""
        return self.treasury.timber + self.treasury.stone
