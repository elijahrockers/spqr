"""Tests for the workshop's nuisance footprint and the per-kind
nuisance radii that drive tier capping.

Workshop nuisance radius is 3 (Chebyshev) — narrower than mill / quarry
which carry 5 tiles. A residence inside a workshop's nuisance zone
caps at huts (tier 1) regardless of materials, road, or office reach."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    INDUSTRIAL_NUISANCE_RADIUS,
    NUISANCE_RADIUS_BY_KIND,
    WORKSHOP_NUISANCE_RADIUS,
    nuisance_radius_for,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.housing import (
    INDUSTRIAL_NUISANCE_KINDS,
    _industrial_nuisance_tiles,
    nuisance_tiles_for,
    nuisance_tiles_for_kind_at,
)


def test_per_kind_nuisance_radii():
    """Workshop emits nuisance over 3 tiles; mill / quarry over 5."""
    assert WORKSHOP_NUISANCE_RADIUS == 3
    assert INDUSTRIAL_NUISANCE_RADIUS == 5
    assert NUISANCE_RADIUS_BY_KIND[BuildingKind.WORKSHOP] == 3
    assert NUISANCE_RADIUS_BY_KIND[BuildingKind.LUMBER_MILL] == 5
    assert NUISANCE_RADIUS_BY_KIND[BuildingKind.QUARRY] == 5
    # Non-industrial kinds return 0 — callers can treat as no zone.
    assert nuisance_radius_for(BuildingKind.RESIDENCE) == 0
    assert nuisance_radius_for(BuildingKind.GRANARY) == 0


def test_workshop_in_nuisance_kinds():
    """The housing system aggregates nuisance from this set; workshop
    must be in it for its zone to actually cap residences."""
    assert BuildingKind.WORKSHOP in INDUSTRIAL_NUISANCE_KINDS


def test_workshop_caps_nearby_residence_at_huts():
    """Residence within the workshop's 3-tile radius must cap at huts
    (tier 1) — the cottage gate is bypassed by the nuisance penalty."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 200.0
    city.treasury.stoneware = 100.0
    # Find a clear strip wide enough for residence + roads + workshop.
    row_y = None
    for y in range(2, city.height - 2):
        if all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in range(1, 6)
        ):
            row_y = y
            break
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=2, y=row_y, kind=ZoneKind.ROAD))
    # Workshop at x=3: Chebyshev distance from residence (x=1) is 2,
    # well inside the 3-tile workshop nuisance zone.
    eng.submit(PlaceZone(x=3, y=row_y, kind=ZoneKind.WORKSHOP))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    workshop = next(b for b in city.buildings if b.kind == BuildingKind.WORKSHOP)
    workshop.completion = 1.0
    for road in [b for b in city.buildings if b.kind == BuildingKind.ROAD]:
        road.completion = 1.0
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier <= 1, (
        f"residence should cap at huts under workshop nuisance, got tier {res.tier}"
    )


def test_distant_workshop_does_not_cap_residence():
    """A workshop more than 3 tiles from a residence (Chebyshev) does
    NOT enter its nuisance zone. Anything else is wrong — the radius
    is the only gate."""
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    # No engine needed — directly check the helper output.
    res_x, res_y = 1, 5
    workshop_x, workshop_y = 5, 5  # Chebyshev distance = 4 > radius 3
    tiles = nuisance_tiles_for_kind_at(
        city, BuildingKind.WORKSHOP, workshop_x, workshop_y,
    )
    assert (res_x, res_y) not in tiles


def test_workshop_nuisance_tiles_form_3_radius_square():
    """Per-building nuisance helper: workshop at (10, 10) should cover
    a 7×7 square (radius-3 Chebyshev) — 49 tiles assuming the city is
    big enough that nothing clips."""
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    eng = Engine(state, default_systems())
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.WORKSHOP))
    eng.step(1)
    workshop = next(b for b in city.buildings if b.kind == BuildingKind.WORKSHOP)
    workshop.completion = 1.0
    tiles = nuisance_tiles_for(city, workshop)
    # 7×7 square, anchored on the workshop tile.
    assert len(tiles) == 49
    assert (workshop.x, workshop.y) in tiles
    assert (workshop.x + 3, workshop.y) in tiles
    assert (workshop.x + 4, workshop.y) not in tiles


def test_mill_and_quarry_nuisance_tiles_form_5_radius_square():
    """Mills and quarries reach 5 tiles — bumped from 4 in this round."""
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    eng = Engine(state, default_systems())
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    # Place a mill with adjacent forest.
    city.tile(11, 10).terrain = CityTerrain.FOREST
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    tiles = nuisance_tiles_for(city, mill)
    # 11×11 square — 121 tiles, assuming none clip the map edge.
    assert len(tiles) == 121
    assert (mill.x + 5, mill.y) in tiles
    assert (mill.x + 6, mill.y) not in tiles


def test_industrial_nuisance_aggregate_uses_per_kind_radii():
    """Combining a mill (radius 5) and a workshop (radius 3) at the
    same anchor produces the union — but the workshop's tiles are a
    subset of the mill's, so the aggregate count should equal the
    mill alone."""
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    eng = Engine(state, default_systems())
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.tile(11, 10).terrain = CityTerrain.FOREST
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.LUMBER_MILL))
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.WORKSHOP))  # rejected (tile occupied)
    eng.step(1)
    # Place workshop at a different spot well outside the mill zone.
    eng.submit(PlaceZone(x=25, y=20, kind=ZoneKind.WORKSHOP))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    workshop = next(b for b in city.buildings if b.kind == BuildingKind.WORKSHOP)
    mill.completion = 1.0
    workshop.completion = 1.0
    aggregate = _industrial_nuisance_tiles(city)
    # Mill: 11×11 = 121 (assuming no clipping). Workshop: 7×7 = 49.
    # No overlap (mill at (10,10), workshop at (25,20) far apart).
    assert len(aggregate) == 121 + 49
