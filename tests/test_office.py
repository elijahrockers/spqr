"""Tests for the OFFICE building: cottage gating in housing and
office-driven taxation in economy.

Office reach scales with assigned workers
(OFFICE_REACH_PER_WORKER × workers). Cottages (tier 2) require an
office in reach to upgrade. Tax revenue comes only from residences
inside the union of all office coverages."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    OFFICE_REACH_PER_WORKER,
    BuildingKind,
    CityTerrain,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.economy import _office_taxable_pops

from ._helpers import find_clear_grass


def _designate_residence_road_office(eng, city, *, residence_x_offset=2):
    """Drop a residence + road + office in a row; hand-finish each so
    tests start from a known operational state. Returns
    (residence, road, office).

    OFFICE is 2×2 — its anchor at (4, row_y) extends into (5, row_y),
    (4, row_y+1), and (5, row_y+1), so the helper checks that those
    tiles are also clear before committing to a row."""
    row_y = None
    for y in range(2, city.height - 3):  # leave room for row_y+1
        # Residence + roads occupy (1..3, row_y); office anchor (4, y)
        # extends through (5, y) and (4..5, y+1).
        row_clear = all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in range(1, 6)
        )
        office_extension_clear = all(
            city.tile(x, y + 1).building_id == -1
            and city.tile(x, y + 1).terrain == CityTerrain.GRASS
            for x in range(4, 6)
        )
        if row_clear and office_extension_clear:
            row_y = y
            break
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=2, y=row_y, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=3, y=row_y, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=4, y=row_y, kind=ZoneKind.OFFICE))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    roads = [b for b in city.buildings if b.kind == BuildingKind.ROAD]
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    for road in roads:
        road.completion = 1.0
    office.completion = 1.0
    return res, roads, office


# --- Cottage gating ---------------------------------------------------------

def test_cottages_blocked_without_office():
    """A residence with road + materials but no office in reach should
    upgrade to huts but stop before cottages."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    # Place residence + road only (no office).
    row_y = None
    for y in range(2, city.height - 2):
        if all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in range(1, 4)
        ):
            row_y = y
            break
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=2, y=row_y, kind=ZoneKind.ROAD))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    road = next(b for b in city.buildings if b.kind == BuildingKind.ROAD)
    road.completion = 1.0
    # Three months: would normally reach tier 3, but no office → cap at 1.
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier == 1, f"expected huts (1), got tier {res.tier}"


def test_cottages_unlocked_with_office_in_reach():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 100.0  # cottages need 50 furniture
    res, _roads, office = _designate_residence_road_office(eng, city)
    # Office needs workers to have any reach. Stuff the district with
    # plebs so labor allocation gives the office its 3 slots.
    city.districts[0].pops.plebs = 50.0
    eng.step(1)  # labor.step assigns workers
    assert office.workers_assigned >= 1
    # Two months should reach tier 2 (cottages) now that the gate opens.
    eng.step(HOURS_PER_MONTH * 2)
    assert res.tier >= 2, f"expected cottages (>=2), got tier {res.tier}"


def test_cottages_blocked_when_office_idle():
    """An office with 0 workers covers nothing — equivalent to no
    office at all for the cottage gate. Drives the housing system
    helper directly so the engine's labor allocation can't fill the
    office mid-test."""
    from spqr.sim.systems.housing import _upgrade_residences

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    res, _roads, office = _designate_residence_road_office(eng, city)
    # Manually advance to huts (would normally happen in a step).
    res.tier = 1
    # Office is staffed by no one — covers nothing.
    office.workers_assigned = 0
    # Housing system attempts the cottage upgrade; gate should block.
    _upgrade_residences(state, city)
    assert res.tier == 1


def test_cottages_unlocked_when_office_staffed():
    """Counterpart: same setup, but with workers_assigned > 0 the
    upgrade goes through. Confirms the gate is purely worker-driven.
    Furniture must be in treasury too — that's the cottage tier cost."""
    from spqr.sim.systems.housing import _upgrade_residences

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 100.0
    res, _roads, office = _designate_residence_road_office(eng, city)
    res.tier = 1
    office.workers_assigned = 3
    _upgrade_residences(state, city)
    assert res.tier == 2


def test_office_reach_scales_with_workers():
    """Verify the reach math: 1 worker = OFFICE_REACH_PER_WORKER cost,
    3 workers = 3× that. The number of tiles in coverage rises
    monotonically with worker count."""
    from spqr.sim.systems.spatial import coverage

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    cov_1 = len(coverage(city, office.x, office.y, OFFICE_REACH_PER_WORKER * 1))
    cov_2 = len(coverage(city, office.x, office.y, OFFICE_REACH_PER_WORKER * 2))
    cov_3 = len(coverage(city, office.x, office.y, OFFICE_REACH_PER_WORKER * 3))
    assert cov_1 < cov_2 < cov_3


# --- Office-driven taxation -------------------------------------------------

def test_no_offices_means_no_tax():
    """Without any offices, the city collects zero tax revenue. Plebs
    in residences contribute nothing."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    city.treasury.denarii = 10_000.0
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    city.districts[0].pops.plebs = 50.0
    plebs, pat = _office_taxable_pops(city)
    assert plebs == 0.0
    assert pat == 0.0


def test_office_in_range_taxes_residences():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    res, _roads, office = _designate_residence_road_office(eng, city)
    office.workers_assigned = 3
    city.districts[0].pops.plebs = 30.0
    plebs, pat = _office_taxable_pops(city)
    # Single residence in district, all plebs in reach → all 30 count.
    assert plebs == 30.0
    assert pat == 0.0


def test_residence_outside_office_reach_pays_no_tax():
    """A residence in the same district as an office but physically
    out of reach should still be untaxed. Verifies the reach gate
    isn't accidentally district-wide."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    # Office in one corner, residence in the opposite corner — well
    # past OFFICE_REACH_PER_WORKER × 1 = 6 cost units even with roads.
    spot_a = (1, 1)
    spot_b = (city.width - 2, city.height - 2)
    eng.submit(PlaceZone(x=spot_a[0], y=spot_a[1], kind=ZoneKind.OFFICE))
    eng.submit(PlaceZone(x=spot_b[0], y=spot_b[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 1  # minimum reach
    city.districts[0].pops.plebs = 10.0
    plebs, _ = _office_taxable_pops(city)
    assert plebs == 0.0


def test_more_office_workers_grow_tax_base():
    """With workers=1 the office covers a small area. With workers=3
    the same office covers proportionally more, capturing residences
    that were previously out of range."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    # Find a row where the office's 2×2 footprint, the close residence,
    # and the far residence all fit on clear grass.
    row_y = None
    for y in range(2, city.height - 3):
        all_clear = all(
            city.tile(x, dy).building_id == -1
            and city.tile(x, dy).terrain == CityTerrain.GRASS
            for x in (1, 2, 4, 11)  # office anchor, office east, close res, far res
            for dy in (y, y + 1)
        )
        if all_clear:
            row_y = y
            break
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.OFFICE))
    eng.submit(PlaceZone(x=4, y=row_y, kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=11, y=row_y, kind=ZoneKind.RESIDENCE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    city.districts[0].pops.plebs = 30.0
    # 1 worker — only the close residence is in reach.
    office.workers_assigned = 1
    p1, _ = _office_taxable_pops(city)
    # 3 workers — both residences in reach.
    office.workers_assigned = 3
    p3, _ = _office_taxable_pops(city)
    assert p3 > p1
