from __future__ import annotations

import enum

import msgspec


class CityTerrain(enum.IntEnum):
    """Terrain at city scale. One tile ~ 30m square."""
    GRASS = 0
    DIRT = 1
    FOREST = 2
    HILL = 3
    WATER = 4
    ROCK = 5
    ROAD = 6


class RegionBiome(enum.IntEnum):
    """Terrain at region scale. One tile ~ 5km square."""
    SEA = 0
    RIVER = 1
    PLAIN = 2
    HILL = 3
    FOREST = 4
    MOUNTAIN = 5
    MARSH = 6


class CityTile(msgspec.Struct, frozen=False):
    terrain: CityTerrain
    # Building id occupying this tile, or -1 if empty. Buildings live on
    # City.buildings; the tile only references them.
    building_id: int = -1


class RegionTile(msgspec.Struct, frozen=False):
    biome: RegionBiome
    elevation: float = 0.0  # 0.0 sea level .. 1.0 mountain peak
    has_road: bool = False
    # Site id of any settlement here, else -1.
    site_id: int = -1
