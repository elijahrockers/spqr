"""Tests for the OFFICE 2×2 footprint placement.

OFFICE is the only multi-tile building. Placement requires all four
tiles in the 2×2 footprint anchored at (x1, y1) to be buildable; cost
is paid once. All four tile.building_ids point to the same office, so
the inspector resolves to the same building from any corner — that's
the third request the user wanted, and it falls out of the shared-id
implementation for free."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, PlaceZoneRect, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BUILDING_COST,
    OFFICE_FOOTPRINT_H,
    OFFICE_FOOTPRINT_W,
    BuildingKind,
)
from spqr.sim.systems import default_systems


def _empty_city():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    return state, eng, city


def test_office_footprint_constants_are_2x2():
    """Pin the footprint shape — if these change, every placement
    test below needs to be rethought."""
    assert OFFICE_FOOTPRINT_W == 2
    assert OFFICE_FOOTPRINT_H == 2


def test_office_placement_occupies_four_tiles():
    state, eng, city = _empty_city()
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    offices = [b for b in city.buildings if b.kind == BuildingKind.OFFICE]
    assert len(offices) == 1
    office = offices[0]
    # All four tiles point to the same office id.
    for dy in range(OFFICE_FOOTPRINT_H):
        for dx in range(OFFICE_FOOTPRINT_W):
            tile = city.tile(office.x + dx, office.y + dy)
            assert tile.building_id == office.id


def test_inspector_resolves_office_from_any_of_four_tiles():
    """Pressing the inspector cursor on any of the 4 office tiles
    should resolve to the same office building. The current inspector
    looks up `tile.building_id` directly — verifying the shared-id
    invariant here pins the user-visible behavior."""
    state, eng, city = _empty_city()
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    seen_ids: set[int] = set()
    for dy in range(OFFICE_FOOTPRINT_H):
        for dx in range(OFFICE_FOOTPRINT_W):
            tile = city.tile(office.x + dx, office.y + dy)
            seen_ids.add(tile.building_id)
    assert seen_ids == {office.id}


def test_office_pays_cost_once():
    state, eng, city = _empty_city()
    cost = BUILDING_COST[BuildingKind.OFFICE]
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    # Cost paid once, not 4× even though the office occupies 4 tiles.
    assert city.treasury.denarii == den_before - cost.denarii
    assert city.treasury.timber == timber_before - cost.timber
    assert city.treasury.stone == stone_before - cost.stone


def test_office_blocked_when_any_footprint_tile_unbuildable():
    """Place a road in the office's intended footprint, then try to
    place the office overlapping. All-or-nothing buildability — the
    placement must be rejected."""
    state, eng, city = _empty_city()
    # Block one tile of the future footprint with a road.
    eng.submit(PlaceZone(x=6, y=5, kind=ZoneKind.ROAD))
    eng.step(1)
    n_before = len(city.buildings)
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    n_after = len(city.buildings)
    # No new office added.
    assert n_after == n_before
    assert all(b.kind != BuildingKind.OFFICE for b in city.buildings)


def test_office_blocked_when_overlapping_existing_office():
    state, eng, city = _empty_city()
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    # Try to place a second office that overlaps the first by one tile.
    eng.submit(PlaceZoneRect(x1=4, y1=4, x2=4, y2=4, kind=ZoneKind.OFFICE))
    eng.step(1)
    offices = [b for b in city.buildings if b.kind == BuildingKind.OFFICE]
    assert len(offices) == 1


def test_rectangle_drag_does_not_apply_to_office():
    """Even if the user passes a wide rectangle, the office placer
    forces 2×2 anchored at (x1, y1). Verifies the engine clamps the
    rectangle for OFFICE rather than spreading offices across it."""
    state, eng, city = _empty_city()
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=10, y2=10, kind=ZoneKind.OFFICE))
    eng.step(1)
    offices = [b for b in city.buildings if b.kind == BuildingKind.OFFICE]
    assert len(offices) == 1
    # Anchor lands at (5, 5); footprint is (5..6, 5..6). No tile in
    # the (7..10, 7..10) range should belong to an office.
    for tile in city.tiles:
        if tile.building_id == -1:
            continue
        b = city.buildings[tile.building_id]
        if b.kind != BuildingKind.OFFICE:
            continue
        # Find which tile this is by index.
        idx = city.tiles.index(tile)
        ty = idx // city.width
        tx = idx % city.width
        assert 5 <= tx <= 6 and 5 <= ty <= 6


def test_office_placement_at_map_edge_rejected():
    """A footprint that would extend off the map (anchor + 1 tile out
    of bounds) must be rejected by the buildability check."""
    state, eng, city = _empty_city()
    # Anchor at the bottom-right corner; footprint extends past the map.
    eng.submit(
        PlaceZoneRect(
            x1=city.width - 1, y1=city.height - 1,
            x2=city.width - 1, y2=city.height - 1,
            kind=ZoneKind.OFFICE,
        )
    )
    eng.step(1)
    offices = [b for b in city.buildings if b.kind == BuildingKind.OFFICE]
    assert len(offices) == 0
