from __future__ import annotations

import random

import numpy as np

from spqr.sim.models import (
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


def generate_city(
    rng: random.Random, region_x: int, region_y: int, city_id: int
) -> City:
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
        # SimCity-style fresh start: no buildings, no grain. The player
        # designates the first residence plot; population migrates in.
        treasury=Resources(grain=0.0, denarii=500.0, timber=80.0, stone=40.0),
    )

    # One starting district owns whatever the player builds. Pops start
    # at zero — plebs migrate in once a residence plot exists.
    pops = PopPool(plebs=0.0, patricians=0.0)
    district = District(id=0, name="Centrum", pops=pops, satisfaction=0.6)
    city.districts.append(district)

    return city
