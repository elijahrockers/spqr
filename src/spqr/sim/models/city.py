from __future__ import annotations

import msgspec

from .building import Building
from .district import District
from .resources import Resources
from .tile import CityTile


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
