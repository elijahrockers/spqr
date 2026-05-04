"""Test helpers — shared setup for the fresh-terrain MVP.

The procgen city now seeds nothing: no buildings, zero pops. Tests that
exercise the running simulation almost always need at least a HOUSE,
a granary, and a wheat farm in place. Designating + waiting for
construction adds tens of ticks of churn to every test, so most callers
want `bootstrap_starter_city` which puts the buildings down and
hand-finishes construction so the test can step from a known
operational baseline."""

from __future__ import annotations

from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import GameState
from spqr.sim.models import BuildingKind, CityTerrain


def find_clear_grass(city, exclude: set[tuple[int, int]] | None = None) -> tuple[int, int]:
    """First (x, y) that's empty grass and not in `exclude`."""
    exclude = exclude or set()
    for y in range(city.height):
        for x in range(city.width):
            if (x, y) in exclude:
                continue
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                return x, y
    raise RuntimeError("no clear grass tile found")


def find_clear_grass_adjacent_to(
    city,
    terrains: set[CityTerrain],
    exclude: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """First (x, y) that's empty grass with at least one orthogonally
    adjacent tile in `terrains`. Used for placing lumber mills (next
    to forest) and quarries (next to hill/rock) in tests, since the
    engine now enforces the adjacency rule on player placements."""
    exclude = exclude or set()
    for y in range(city.height):
        for x in range(city.width):
            if (x, y) in exclude:
                continue
            t = city.tile(x, y)
            if t.building_id != -1 or t.terrain != CityTerrain.GRASS:
                continue
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if not city.in_bounds(nx, ny):
                    continue
                if city.tile(nx, ny).terrain in terrains:
                    return x, y
    raise RuntimeError(
        f"no clear grass tile adjacent to {terrains} found"
    )


def paint_adjacent_terrain(
    city, x: int, y: int, terrain: CityTerrain,
) -> None:
    """Force one orthogonally-adjacent tile of (x, y) to `terrain`,
    so the engine's mill/quarry adjacency check passes when the
    test wants a building at a specific spot. Picks the first
    adjacent in-bounds tile that isn't already a building or
    something the test cares about. Test-only — mutates the
    procgen-frozen tilemap directly."""
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + dx, y + dy
        if not city.in_bounds(nx, ny):
            continue
        t = city.tile(nx, ny)
        if t.building_id != -1:
            continue
        t.terrain = terrain
        return
    raise RuntimeError(f"no free neighbor for ({x},{y}) to paint")


def bootstrap_starter_city(
    state: GameState,
    eng: Engine,
    *,
    plebs: float = 50.0,
    grain_stocked: float = 2500.0,
) -> dict[str, object]:
    """Designate a starter set (1 HOUSE + 1 FARM + 1 GRANARY), seed pleb
    pop, hand-finish the FARM + GRANARY, and stockpile the granary.

    Returns a dict with handles `{"house", "farm", "granary"}`."""
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    used: set[tuple[int, int]] = set()
    house_xy = find_clear_grass(city, used)
    used.add(house_xy)
    farm_xy = find_clear_grass(city, used)
    used.add(farm_xy)
    gran_xy = find_clear_grass(city, used)
    used.add(gran_xy)
    eng.submit(PlaceZone(x=house_xy[0], y=house_xy[1], kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=farm_xy[0], y=farm_xy[1], kind=ZoneKind.FARM))
    eng.submit(PlaceZone(x=gran_xy[0], y=gran_xy[1], kind=ZoneKind.GRANARY))
    eng.step(1)
    house = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    farm.completion = 1.0
    granary.completion = 1.0
    granary.grain_stored = grain_stocked
    city.districts[0].pops.plebs = plebs
    return {"house": house, "farm": farm, "granary": granary}
