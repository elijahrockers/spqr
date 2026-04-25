from __future__ import annotations

import random

import numpy as np

from spqr.sim.models import (
    Building,
    BuildingKind,
    City,
    CityTerrain,
    CityTile,
    Citizen,
    CitizenRole,
    District,
    GarrisonState,
    PopPool,
    Resources,
)

from .names import city_name, roman_name


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


def _find_buildable_spot(
    terrain: np.ndarray, occupied: set[tuple[int, int]], rng: random.Random
) -> tuple[int, int] | None:
    """Find a grass/dirt tile not currently occupied. Picks randomly among
    the closest 50 candidates to map center for compact early layout."""
    candidates: list[tuple[int, int]] = []
    cy, cx = CITY_H // 2, CITY_W // 2
    for y in range(CITY_H):
        for x in range(CITY_W):
            if (y, x) in occupied:
                continue
            t = terrain[y, x]
            if t in (int(CityTerrain.GRASS), int(CityTerrain.DIRT)):
                candidates.append((y, x))
    if not candidates:
        return None
    candidates.sort(key=lambda yx: (yx[0] - cy) ** 2 + (yx[1] - cx) ** 2)
    pool = candidates[: min(len(candidates), 50)]
    return rng.choice(pool)


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
        # Grain is the cached aggregate of granary inventories; the actual
        # starter stockpile is set on the granary below.
        treasury=Resources(grain=0.0, denarii=500.0, timber=80.0, stone=40.0),
        garrison=GarrisonState(legionaries=10, auxiliaries=0, training=0.4),
    )

    # One starting district that owns the initial pop pool. Later milestones
    # will subdivide districts as the city grows.
    pops = PopPool(slaves=10.0, plebs=50.0, equites=4.0, patricians=1.0)
    district = District(id=0, name="Centrum", pops=pops, satisfaction=0.6)
    city.districts.append(district)

    occupied: set[tuple[int, int]] = set()

    def place(kind: BuildingKind, completion: float = 1.0) -> Building | None:
        spot = _find_buildable_spot(terrain, occupied, rng)
        if spot is None:
            return None
        y, x = spot
        building = Building(
            id=city.next_building_id,
            kind=kind,
            x=x,
            y=y,
            workers_assigned=0,
            completion=completion,
        )
        city.next_building_id += 1
        city.buildings.append(building)
        idx = y * CITY_W + x
        city.tiles[idx].building_id = building.id
        district.building_ids.append(building.id)
        occupied.add((y, x))
        return building

    place(BuildingKind.FORUM)
    for _ in range(4):
        place(BuildingKind.INSULA)
    place(BuildingKind.BARRACKS)
    for _ in range(3):
        place(BuildingKind.FARM)
    starter_granary = place(BuildingKind.GRANARY)
    if starter_granary is not None:
        # Granaries are now the canonical grain store; treasury.grain is a
        # cached aggregate. Stockpile sized to last from the January
        # founding through the first harvests in March-April with a small
        # safety margin.
        starter_granary.grain_stored = 2500.0
        city.treasury.grain = 2500.0

    # Seed one named magistrate as the inaugural agent.
    magistrate = Citizen(
        id=city.next_citizen_id,
        name=roman_name(rng),
        role=CitizenRole.MAGISTRATE,
        age=rng.randint(35, 55),
        ambition=rng.uniform(-0.3, 0.7),
        competence=rng.uniform(0.0, 0.8),
        piety=rng.uniform(-0.2, 0.6),
        role_since_tick=0,
    )
    city.next_citizen_id += 1
    city.citizens.append(magistrate)

    return city
