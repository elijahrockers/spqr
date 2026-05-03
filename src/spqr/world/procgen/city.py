from __future__ import annotations

import random

import numpy as np

from spqr.sim.models import (
    Building,
    BuildingKind,
    City,
    CityTerrain,
    CityTile,
    District,
    PopPool,
    Resources,
)

from .names import city_name


CITY_W = 60
CITY_H = 30


# 11×3 starter block. The lumber mill and quarry are pushed all the
# way to the right so they sit > INDUSTRIAL_NUISANCE_RADIUS (4)
# Chebyshev tiles from every residence — without that buffer the
# residences would cap at huts from day one.
#
#   col:     0 1 2 3 4 5 6 7 8 9 10
#   row 0:   F F F G W . . . . L  Q
#   row 1:   = = = = = = = = = =  =
#   row 2:   R R R F F F . . . .  .
#
# Closest residence (2, 2) to mill (9, 0): max(7, 2) = 7 — safely out
# of nuisance range.
_STARTER_LAYOUT: list[tuple[BuildingKind, int, int]] = [
    # Row 0 — production cluster on the left, industry on the right
    (BuildingKind.FARM,        0, 0),
    (BuildingKind.FARM,        1, 0),
    (BuildingKind.FARM,        2, 0),
    (BuildingKind.GRANARY,     3, 0),
    (BuildingKind.WAREHOUSE,   4, 0),
    (BuildingKind.LUMBER_MILL, 9, 0),
    (BuildingKind.QUARRY,     10, 0),
    # Row 1 — paved road spans the whole strip, connecting industry
    # to the rest of the block.
    (BuildingKind.ROAD,        0, 1),
    (BuildingKind.ROAD,        1, 1),
    (BuildingKind.ROAD,        2, 1),
    (BuildingKind.ROAD,        3, 1),
    (BuildingKind.ROAD,        4, 1),
    (BuildingKind.ROAD,        5, 1),
    (BuildingKind.ROAD,        6, 1),
    (BuildingKind.ROAD,        7, 1),
    (BuildingKind.ROAD,        8, 1),
    (BuildingKind.ROAD,        9, 1),
    (BuildingKind.ROAD,       10, 1),
    # Row 2 — residences on the left, farms middle. Right end empty
    # so the player has somewhere to put an office.
    (BuildingKind.RESIDENCE,   0, 2),
    (BuildingKind.RESIDENCE,   1, 2),
    (BuildingKind.RESIDENCE,   2, 2),
    (BuildingKind.FARM,        3, 2),
    (BuildingKind.FARM,        4, 2),
    (BuildingKind.FARM,        5, 2),
]
_STARTER_BLOCK_W = 11
_STARTER_BLOCK_H = 3


def _terrain_field(rng: random.Random) -> np.ndarray:
    """Generate a city-scale terrain map. Mostly grass with patches of forest,
    hill, water, and rock."""
    seed = rng.getrandbits(32)
    nprng = np.random.default_rng(seed)
    # Two octaves of noise: large biome blobs + finer texture.
    big = nprng.random((CITY_H // 4 + 1, CITY_W // 4 + 1))
    small = nprng.random((CITY_H, CITY_W))
    ys = np.linspace(0, big.shape[0] - 1, CITY_H)
    xs = np.linspace(0, big.shape[1] - 1, CITY_W)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    y1 = np.clip(y0 + 1, 0, big.shape[0] - 1)
    x1 = np.clip(x0 + 1, 0, big.shape[1] - 1)
    ty = (ys - y0)[:, None]
    tx = (xs - x0)[None, :]
    a = big[np.ix_(y0, x0)]
    b = big[np.ix_(y0, x1)]
    c = big[np.ix_(y1, x0)]
    d = big[np.ix_(y1, x1)]
    upscaled = a * (1 - ty) * (1 - tx) + b * (1 - ty) * tx + c * ty * (1 - tx) + d * ty * tx
    field = 0.7 * upscaled + 0.3 * small
    field -= field.min()
    field /= max(1e-9, field.max())

    terrain = np.full((CITY_H, CITY_W), int(CityTerrain.GRASS), dtype=np.int8)
    terrain[field < 0.10] = int(CityTerrain.WATER)
    terrain[(field >= 0.10) & (field < 0.18)] = int(CityTerrain.DIRT)
    terrain[(field >= 0.65) & (field < 0.80)] = int(CityTerrain.FOREST)
    terrain[(field >= 0.80) & (field < 0.92)] = int(CityTerrain.HILL)
    terrain[field >= 0.92] = int(CityTerrain.ROCK)
    return terrain


def _find_buildable_block(
    terrain: np.ndarray, w: int, h: int
) -> tuple[int, int] | None:
    """Find the top-left (x, y) of an unoccupied w×h rectangle of
    grass/dirt tiles whose center is closest to the map center. Returns
    None if no such block exists (rare on default terrain)."""
    cy_target, cx_target = CITY_H // 2, CITY_W // 2
    best: tuple[int, int] | None = None
    best_dist = float("inf")
    buildable_ids = (int(CityTerrain.GRASS), int(CityTerrain.DIRT))
    for y0 in range(CITY_H - h + 1):
        for x0 in range(CITY_W - w + 1):
            block = terrain[y0:y0 + h, x0:x0 + w]
            ok = True
            for cell in block.flat:
                if cell not in buildable_ids:
                    ok = False
                    break
            if not ok:
                continue
            cy_block = y0 + h // 2
            cx_block = x0 + w // 2
            dist = (cy_block - cy_target) ** 2 + (cx_block - cx_target) ** 2
            if dist < best_dist:
                best_dist = dist
                best = (x0, y0)
    return best


def generate_city(
    rng: random.Random,
    region_x: int,
    region_y: int,
    city_id: int,
    *,
    seed_starter: bool = True,
) -> City:
    """Build a city with random terrain. With `seed_starter=True`
    (the production default), drop an 11×3 starter block of residences
    + farms + granary + warehouse + lumber mill + quarry + road into
    the most central buildable area. Industrial buildings sit at the
    far right of the block so residences are outside
    INDUSTRIAL_NUISANCE_RADIUS. Tests that need a clean slate pass
    `seed_starter=False`."""
    terrain = _terrain_field(rng)
    tiles = [
        CityTile(terrain=CityTerrain(int(terrain[y, x])), building_id=-1)
        for y in range(CITY_H)
        for x in range(CITY_W)
    ]

    city = City(
        id=city_id,
        name=city_name(rng),
        region_x=region_x,
        region_y=region_y,
        width=CITY_W,
        height=CITY_H,
        tiles=tiles,
        # Starting reserves cover initial designations beyond the seeded
        # block. Mills + quarries are required to refill these.
        treasury=Resources(grain=0.0, denarii=500.0, timber=80.0, stone=40.0),
    )

    # One starting district owns the seeded block (and anything the
    # player builds later). Pops start at zero — plebs migrate in once
    # the residences are reachable.
    pops = PopPool(plebs=0.0, patricians=0.0)
    district = District(id=0, name="Centrum", pops=pops, satisfaction=0.6)
    city.districts.append(district)

    if seed_starter:
        _place_starter_block(city, terrain, district)

    return city


def _place_starter_block(
    city: City, terrain: np.ndarray, district: District
) -> None:
    """Find the most central 6×3 buildable rectangle and stamp the
    starter block into it. Buildings are placed at completion=1.0 so
    the player can use them immediately."""
    spot = _find_buildable_block(terrain, _STARTER_BLOCK_W, _STARTER_BLOCK_H)
    if spot is None:
        # No flat 6×3 block on this map; leave empty. The player can
        # still build manually.
        return
    x0, y0 = spot
    for kind, dx, dy in _STARTER_LAYOUT:
        x = x0 + dx
        y = y0 + dy
        building = Building(
            id=city.next_building_id,
            kind=kind,
            x=x,
            y=y,
            completion=1.0,
        )
        city.next_building_id += 1
        city.buildings.append(building)
        city.tiles[y * CITY_W + x].building_id = building.id
        district.building_ids.append(building.id)
