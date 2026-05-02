from __future__ import annotations

import random

import numpy as np

from spqr.sim.models import NeighborSite, Province, RegionBiome, RegionTile


REGION_W = 32
REGION_H = 32


def _fractal_noise(rng: random.Random, w: int, h: int, octaves: int = 4) -> np.ndarray:
    """Sum of upscaled random grids at increasing resolution. Output normalized
    to [0, 1]. Deterministic given rng (numpy seed derived from stdlib rng)."""
    seed = rng.getrandbits(32)
    nprng = np.random.default_rng(seed)
    field = np.zeros((h, w), dtype=np.float64)
    amplitude = 1.0
    total = 0.0
    for octave in range(octaves):
        scale = 2 ** (octave + 1)
        gh = max(2, h // scale)
        gw = max(2, w // scale)
        small = nprng.random((gh, gw))
        # Bilinear-like upscale via numpy: index by float coords and round.
        ys = np.linspace(0, gh - 1, h)
        xs = np.linspace(0, gw - 1, w)
        y0 = np.floor(ys).astype(int)
        x0 = np.floor(xs).astype(int)
        y1 = np.clip(y0 + 1, 0, gh - 1)
        x1 = np.clip(x0 + 1, 0, gw - 1)
        ty = (ys - y0)[:, None]
        tx = (xs - x0)[None, :]
        a = small[np.ix_(y0, x0)]
        b = small[np.ix_(y0, x1)]
        c = small[np.ix_(y1, x0)]
        d = small[np.ix_(y1, x1)]
        upscaled = a * (1 - ty) * (1 - tx) + b * (1 - ty) * tx + c * ty * (1 - tx) + d * ty * tx
        field += amplitude * upscaled
        total += amplitude
        amplitude *= 0.5
    field /= total
    field -= field.min()
    field /= max(1e-9, field.max())
    return field


def _biome_for(elev: float) -> RegionBiome:
    if elev < 0.25:
        return RegionBiome.SEA
    if elev < 0.30:
        return RegionBiome.MARSH
    if elev < 0.50:
        return RegionBiome.PLAIN
    if elev < 0.70:
        return RegionBiome.HILL
    if elev < 0.85:
        return RegionBiome.FOREST
    return RegionBiome.MOUNTAIN


def _carve_river(elev: np.ndarray, biomes: np.ndarray) -> None:
    """Pick a high point and walk downhill to the lowest neighbor; mark each
    visited cell as RIVER (stopping at sea). Mutates `biomes` in place."""
    h, w = elev.shape
    # Start from a random-ish high point: highest value in the upper half.
    upper = elev[: h // 2, :]
    yi, xi = np.unravel_index(np.argmax(upper), upper.shape)
    y, x = int(yi), int(xi)
    visited: set[tuple[int, int]] = set()
    while 0 <= y < h and 0 <= x < w:
        if (y, x) in visited:
            break
        visited.add((y, x))
        if biomes[y, x] == RegionBiome.SEA:
            break
        biomes[y, x] = RegionBiome.RIVER
        # Pick the lowest 4-neighbor (greedy descent).
        best = None
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and (ny, nx) not in visited:
                if best is None or elev[ny, nx] < elev[best[0], best[1]]:
                    best = (ny, nx)
        if best is None or elev[best[0], best[1]] >= elev[y, x]:
            break
        y, x = best


def _pick_city_site(biomes: np.ndarray, rng: random.Random) -> tuple[int, int]:
    """Prefer plain tiles adjacent to river; fall back to any plain or hill
    not on the map edge."""
    h, w = biomes.shape
    near_river: list[tuple[int, int]] = []
    plain_or_hill: list[tuple[int, int]] = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            b = biomes[y, x]
            if b not in (RegionBiome.PLAIN, RegionBiome.HILL):
                continue
            plain_or_hill.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if biomes[y + dy, x + dx] == RegionBiome.RIVER:
                        near_river.append((y, x))
                        break
                else:
                    continue
                break
    pool = near_river or plain_or_hill
    if not pool:
        # Pathological map: just use the center.
        return h // 2, w // 2
    return rng.choice(pool)


def generate_region(rng: random.Random) -> tuple[Province, tuple[int, int]]:
    """Generate a region map and return (province, (city_y, city_x)).

    The caller is responsible for adding the player city to province.sites
    after constructing the City model."""
    elev = _fractal_noise(rng, REGION_W, REGION_H)
    biomes = np.empty(elev.shape, dtype=np.int8)
    for y in range(elev.shape[0]):
        for x in range(elev.shape[1]):
            biomes[y, x] = int(_biome_for(float(elev[y, x])))
    _carve_river(elev, biomes)
    cy, cx = _pick_city_site(biomes, rng)

    tiles: list[RegionTile] = []
    for y in range(REGION_H):
        for x in range(REGION_W):
            tiles.append(
                RegionTile(
                    biome=RegionBiome(int(biomes[y, x])),
                    elevation=float(elev[y, x]),
                    has_road=False,
                    site_id=-1,
                )
            )

    sites: list[NeighborSite] = []
    province = Province(width=REGION_W, height=REGION_H, tiles=tiles, sites=sites)
    return province, (cy, cx)
