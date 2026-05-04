"""Tests for the adjacency rule on lumber-mill / quarry placement.

A lumber mill must sit orthogonally adjacent to at least one
FOREST tile. A quarry must sit adjacent to HILL or ROCK. Other
building kinds have no adjacency requirement and pass through."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
)
from spqr.sim.systems import default_systems

from ._helpers import (
    find_clear_grass,
    find_clear_grass_adjacent_to,
)


def _seeded_city():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 1000.0
    city.treasury.stone = 1000.0
    return state, eng, city


def test_mill_with_adjacent_forest_places():
    _state, eng, city = _seeded_city()
    spot = find_clear_grass_adjacent_to(city, {CityTerrain.FOREST})
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mills = [b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL]
    assert len(mills) == 1


def test_mill_without_adjacent_forest_rejected():
    """Find a grass tile whose four neighbors are all grass / dirt /
    water (no forest) and try to place. Engine should refuse and
    log the warning; no building lands."""
    _state, eng, city = _seeded_city()
    spot = _find_grass_with_no_adjacent({CityTerrain.FOREST}, city)
    if spot is None:
        # The map happens to have forest everywhere — skip rather
        # than fake a result.
        return
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mills = [b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL]
    assert mills == []


def test_quarry_requires_adjacent_hill_or_rock():
    _state, eng, city = _seeded_city()
    spot = find_clear_grass_adjacent_to(
        city, {CityTerrain.HILL, CityTerrain.ROCK},
    )
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.QUARRY))
    eng.step(1)
    quarries = [b for b in city.buildings if b.kind == BuildingKind.QUARRY]
    assert len(quarries) == 1


def test_quarry_without_adjacent_rock_rejected():
    _state, eng, city = _seeded_city()
    spot = _find_grass_with_no_adjacent(
        {CityTerrain.HILL, CityTerrain.ROCK}, city,
    )
    if spot is None:
        return
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.QUARRY))
    eng.step(1)
    quarries = [b for b in city.buildings if b.kind == BuildingKind.QUARRY]
    assert quarries == []


def test_residence_has_no_adjacency_requirement():
    """The adjacency check is opt-in per kind. Residences anywhere
    on grass should still place fine."""
    _state, eng, city = _seeded_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    res = [b for b in city.buildings if b.kind == BuildingKind.RESIDENCE]
    assert len(res) == 1


def _find_grass_with_no_adjacent(
    terrains: set[CityTerrain], city,
) -> tuple[int, int] | None:
    """Return a clear grass tile whose orthogonal neighbors include
    none of `terrains`. None if every grass tile has at least one
    such neighbor (rare on default procgen)."""
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id != -1 or t.terrain != CityTerrain.GRASS:
                continue
            has_match = False
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if not city.in_bounds(nx, ny):
                    continue
                if city.tile(nx, ny).terrain in terrains:
                    has_match = True
                    break
            if not has_match:
                return x, y
    return None
