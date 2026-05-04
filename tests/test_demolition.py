"""Tests for the BULLDOZE tool.

Bulldoze handles both removal cases:
  Under construction — free, full BUILDING_COST refund (denarii + materials).
  Completed         — costs BULLDOZE_DENARII_COST, refunds
                      BULLDOZE_REFUND_FRACTION of timber+stone (no denarii back).

Multi-tile buildings (office) are removed as one unit and charged/refunded once."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, PlaceZoneRect, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BUILDING_COST,
    BULLDOZE_DENARII_COST,
    BULLDOZE_REFUND_FRACTION,
    BuildingKind,
)
from spqr.sim.systems import default_systems

from ._helpers import find_clear_grass


def _empty_city():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 1000.0
    city.treasury.stone = 1000.0
    return state, eng, city


# --- Under-construction (free) -----------------------------------------------

def test_bulldoze_under_construction_refunds_full_cost():
    """Bulldozing a building still under construction is free: all
    denarii, timber, and stone come back in full."""
    _state, eng, city = _empty_city()
    spot = find_clear_grass(city)
    cost = BUILDING_COST[BuildingKind.WORKSHOP]
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WORKSHOP))
    eng.step(1)
    assert city.treasury.denarii == den_before - cost.denarii
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.BULLDOZE))
    eng.step(1)
    # Full refund — back to the original amounts.
    assert city.treasury.denarii == den_before
    assert city.treasury.timber == timber_before
    assert city.treasury.stone == stone_before
    # Building tombstoned; tile clear.
    workshops = [b for b in city.buildings if b.kind == BuildingKind.WORKSHOP]
    assert len(workshops) == 0
    assert city.tile(spot[0], spot[1]).building_id == -1


def test_bulldoze_under_construction_office_clears_all_four_tiles():
    """A multi-tile office cancelled via bulldoze must clear all 4 tiles
    and refund the full cost exactly once."""
    _state, eng, city = _empty_city()
    cost = BUILDING_COST[BuildingKind.OFFICE]
    den_before = city.treasury.denarii
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    # Cursor on the far corner — same building should be removed.
    eng.submit(PlaceZone(x=6, y=6, kind=ZoneKind.BULLDOZE))
    eng.step(1)
    # Full cost returned exactly once.
    assert city.treasury.denarii == den_before
    # All 4 footprint tiles cleared.
    for dy in range(2):
        for dx in range(2):
            assert city.tile(5 + dx, 5 + dy).building_id == -1
    assert office.kind == BuildingKind.EMPTY


def test_bulldoze_rect_cancels_multiple_under_construction():
    """Drag-bulldoze over a rectangle cancels every under-construction
    building inside with a single command."""
    _state, eng, city = _empty_city()
    eng.submit(PlaceZoneRect(x1=2, y1=2, x2=4, y2=2, kind=ZoneKind.FARM))
    eng.step(1)
    n_farms_before = sum(1 for b in city.buildings if b.kind == BuildingKind.FARM)
    assert n_farms_before > 0
    eng.submit(PlaceZoneRect(x1=2, y1=2, x2=4, y2=2, kind=ZoneKind.BULLDOZE))
    eng.step(1)
    n_farms_after = sum(1 for b in city.buildings if b.kind == BuildingKind.FARM)
    assert n_farms_after == 0


# --- Completed (paid) --------------------------------------------------------

def test_bulldoze_charges_fee_and_refunds_half_materials():
    _state, eng, city = _empty_city()
    spot = find_clear_grass(city)
    cost = BUILDING_COST[BuildingKind.GRANARY]
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.GRANARY))
    eng.step(1)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.completion = 1.0
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.BULLDOZE))
    eng.step(1)
    # Fee deducted; no denarii refund.
    assert city.treasury.denarii == den_before - BULLDOZE_DENARII_COST
    # 50% of original materials back.
    assert city.treasury.timber == timber_before + cost.timber * BULLDOZE_REFUND_FRACTION
    assert city.treasury.stone == stone_before + cost.stone * BULLDOZE_REFUND_FRACTION
    assert city.tile(spot[0], spot[1]).building_id == -1
    assert granary.kind == BuildingKind.EMPTY


def test_bulldoze_skips_when_treasury_too_low():
    """If denarii < BULLDOZE_DENARII_COST for a completed building, the
    attempt is a no-op and the building remains."""
    _state, eng, city = _empty_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.GRANARY))
    eng.step(1)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.completion = 1.0
    city.treasury.denarii = BULLDOZE_DENARII_COST - 1.0
    timber_before = city.treasury.timber
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.BULLDOZE))
    eng.step(1)
    assert granary.kind == BuildingKind.GRANARY
    assert city.tile(spot[0], spot[1]).building_id == granary.id
    assert city.treasury.timber == timber_before


def test_bulldoze_office_charges_once_for_2x2():
    """Bulldozing a completed 2×2 office costs BULLDOZE_DENARII_COST
    once (not 4×) and refunds materials once."""
    _state, eng, city = _empty_city()
    cost = BUILDING_COST[BuildingKind.OFFICE]
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=5, y2=5, kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    eng.submit(PlaceZoneRect(x1=5, y1=5, x2=6, y2=6, kind=ZoneKind.BULLDOZE))
    eng.step(1)
    assert city.treasury.denarii == den_before - BULLDOZE_DENARII_COST
    assert city.treasury.timber == timber_before + cost.timber * BULLDOZE_REFUND_FRACTION
    assert city.treasury.stone == stone_before + cost.stone * BULLDOZE_REFUND_FRACTION
    assert office.kind == BuildingKind.EMPTY


# --- Tombstone safety --------------------------------------------------------

def test_tombstoned_building_id_does_not_break_iteration():
    """After removal, city.buildings keeps the slot as a tombstone
    (kind=EMPTY) so existing tile.building_id values stay stable."""
    _state, eng, city = _empty_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.GRANARY))
    eng.step(1)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.completion = 1.0
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.BULLDOZE))
    eng.step(1)
    assert any(b.kind == BuildingKind.EMPTY for b in city.buildings)
    granaries = list(city.completed_of(BuildingKind.GRANARY))
    assert len(granaries) == 0
