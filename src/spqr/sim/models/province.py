from __future__ import annotations

import enum

import msgspec

from .tile import RegionTile


class SiteKind(enum.IntEnum):
    PLAYER_CITY = 0
    ALLIED_VILLAGE = 1


class NeighborSite(msgspec.Struct, frozen=False):
    id: int
    name: str
    kind: SiteKind
    region_x: int
    region_y: int


class Province(msgspec.Struct, frozen=False):
    width: int
    height: int
    # Row-major region tilemap; len = width * height.
    tiles: list[RegionTile]
    sites: list[NeighborSite] = msgspec.field(default_factory=list)

    def tile(self, x: int, y: int) -> RegionTile:
        return self.tiles[y * self.width + x]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height
