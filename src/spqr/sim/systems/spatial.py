"""Spatial reach helpers — used by the grain system to compute granary
coverage areas and farm-to-granary connections.

Implementation: small Dijkstra from a start tile across the city tilemap.
Roads are cheap (cost 1 to enter), plain tiles passable but slow (cost
2.5), buildings passable at intermediate cost (2.0), water and rock are
impassable. The cost cap caller-supplied; only tiles whose cumulative
entry cost is ≤ cap are returned."""

from __future__ import annotations

import heapq

from spqr.sim.models import BuildingKind, City, CityTerrain


# Per-tile entry cost. Lower = easier to traverse.
ROAD_COST = 1.0
BUILDING_COST_NON_ROAD = 2.0
PLAIN_COST = 2.5
IMPASSABLE_TERRAIN: frozenset[CityTerrain] = frozenset(
    {CityTerrain.WATER, CityTerrain.ROCK}
)


def coverage(city: City, start_x: int, start_y: int, max_cost: float) -> dict[tuple[int, int], float]:
    """Return {(x, y): cumulative cost} for every tile reachable from
    (start_x, start_y) within max_cost. The start tile itself is at cost 0.

    Iteration is deterministic: heapq breaks ties by (cost, x, y) tuple
    order, and neighbor expansion follows a fixed N/E/S/W order."""
    result: dict[tuple[int, int], float] = {(start_x, start_y): 0.0}
    frontier: list[tuple[float, int, int]] = [(0.0, start_x, start_y)]
    while frontier:
        cost, x, y = heapq.heappop(frontier)
        # If we've already found a shorter path, skip.
        if cost > result.get((x, y), float("inf")):
            continue
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not city.in_bounds(nx, ny):
                continue
            tile = city.tiles[ny * city.width + nx]
            if tile.terrain in IMPASSABLE_TERRAIN:
                continue
            step = _step_cost(city, tile)
            new_cost = cost + step
            if new_cost > max_cost:
                continue
            prev = result.get((nx, ny), float("inf"))
            if new_cost < prev:
                result[(nx, ny)] = new_cost
                heapq.heappush(frontier, (new_cost, nx, ny))
    return result


def _step_cost(city: City, tile) -> float:  # type: ignore[no-untyped-def]
    if tile.building_id != -1:
        b = city.buildings[tile.building_id]
        if b.kind == BuildingKind.ROAD:
            return ROAD_COST
        return BUILDING_COST_NON_ROAD
    return PLAIN_COST
