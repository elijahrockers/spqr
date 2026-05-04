"""Tests for the industrial-nuisance mechanic.

A residence within INDUSTRIAL_NUISANCE_RADIUS (Chebyshev) of any
completed quarry or lumber mill is capped at huts (tier 1) and
contributes a monthly satisfaction penalty proportional to the
fraction of district residences in the nuisance zone."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH,
    INDUSTRIAL_NUISANCE_RADIUS,
    BuildingKind,
    CityTerrain,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.housing import (
    _apply_industrial_nuisance,
    _industrial_nuisance_tiles,
)

from ._helpers import paint_adjacent_terrain


def _empty_city():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 200.0
    # Cottages now require furniture; insulae require stoneware. Seed
    # generously so nuisance tests aren't gated on production setup.
    city.treasury.furniture = 200.0
    city.treasury.stoneware = 100.0
    return state, eng, city


def _designate_residence_road_office_and_industry(eng, city, *, with_mill=True):
    """Lay out: residence + adjacent road + nearby office (so office
    reach covers the residence, allowing tier 2 upgrades) + a lumber
    mill near the residence (within nuisance radius). Returns
    (residence, mill | None).

    Office is 2×2 — its anchor at (7, row_y) extends to (8, row_y)
    and (7..8, row_y+1). Mill (when present) sits at (4, row_y - 1).
    The row search must verify all of those tiles are clear."""
    row_y = None
    for y in range(2, city.height - 3):
        # The whole row + the office's row_y+1 extension + the mill's
        # row_y-1 spot all need to be clear grass.
        row_clear = all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in range(1, 12)
        )
        office_ext_clear = all(
            city.tile(x, y + 1).building_id == -1
            and city.tile(x, y + 1).terrain == CityTerrain.GRASS
            for x in range(7, 9)
        )
        mill_clear = (
            not with_mill
            or (
                y >= 1
                and city.tile(4, y - 1).building_id == -1
                and city.tile(4, y - 1).terrain == CityTerrain.GRASS
            )
        )
        if row_clear and office_ext_clear and mill_clear:
            row_y = y
            break
    assert row_y is not None
    # x=1 residence, x=2..6 roads, x=7 office (2×2 anchor), x=4 row_y-1 mill.
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    for x in range(2, 7):
        eng.submit(PlaceZone(x=x, y=row_y, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=7, y=row_y, kind=ZoneKind.OFFICE))
    if with_mill:
        # Mill at x=4: Chebyshev distance from residence (x=1) is 3,
        # which is < INDUSTRIAL_NUISANCE_RADIUS=5, so the residence
        # falls in the nuisance zone. The engine requires forest
        # adjacent to the mill — paint one in.
        paint_adjacent_terrain(city, 4, row_y - 1, CityTerrain.FOREST)
        eng.submit(PlaceZone(x=4, y=row_y - 1, kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    for road in [b for b in city.buildings if b.kind == BuildingKind.ROAD]:
        road.completion = 1.0
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 3
    mill = None
    if with_mill:
        mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
        mill.completion = 1.0
    return res, mill


# --- Tier cap ---------------------------------------------------------------

def test_residence_in_nuisance_caps_at_huts():
    """Residence near a lumber mill should reach huts (tier 1) but
    never advance to cottages even with road, office, and materials."""
    _state, eng, city = _empty_city()
    res, mill = _designate_residence_road_office_and_industry(eng, city)
    assert mill is not None
    # Three months: would reach cottages without the mill.
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier == 1


def test_same_layout_without_mill_reaches_cottages():
    """Sanity check: drop the mill, same starter, residence reaches
    tier 2 — confirms the mill is the gate, not some other limit."""
    _state, eng, city = _empty_city()
    res, _ = _designate_residence_road_office_and_industry(eng, city, with_mill=False)
    # Seed plebs so labor.step actually staffs the office (cottage
    # gate requires office reach, which scales with assigned workers).
    city.districts[0].pops.plebs = 10.0
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier >= 2


def test_quarry_also_triggers_nuisance():
    """Both quarry and lumber mill emit nuisance — verify the quarry
    branch isn't accidentally lumber-mill-only."""
    _state, eng, city = _empty_city()
    row_y = _find_clear_row_with_office_and_quarry_space(city)
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    for x in range(2, 7):
        eng.submit(PlaceZone(x=x, y=row_y, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=7, y=row_y, kind=ZoneKind.OFFICE))
    paint_adjacent_terrain(city, 4, row_y - 1, CityTerrain.HILL)
    eng.submit(PlaceZone(x=4, y=row_y - 1, kind=ZoneKind.QUARRY))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    for road in [b for b in city.buildings if b.kind == BuildingKind.ROAD]:
        road.completion = 1.0
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 3
    quarry = next(b for b in city.buildings if b.kind == BuildingKind.QUARRY)
    quarry.completion = 1.0
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier == 1


def _find_clear_row_with_office_and_quarry_space(city):
    """Same shape as the helper above: row + office row+1 extension +
    quarry/mill row-1 spot all clear."""
    for y in range(2, city.height - 3):
        row_clear = all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in range(1, 12)
        )
        office_ext = all(
            city.tile(x, y + 1).building_id == -1
            and city.tile(x, y + 1).terrain == CityTerrain.GRASS
            for x in range(7, 9)
        )
        ind_clear = (
            y >= 1
            and city.tile(4, y - 1).building_id == -1
            and city.tile(4, y - 1).terrain == CityTerrain.GRASS
        )
        if row_clear and office_ext and ind_clear:
            return y
    return None


def test_distant_mill_does_not_trigger_nuisance():
    """A mill outside INDUSTRIAL_NUISANCE_RADIUS must NOT cap the
    residence — the radius is the only thing gating the effect."""
    _state, eng, city = _empty_city()
    # Put the mill far enough away that Chebyshev distance > radius.
    far = INDUSTRIAL_NUISANCE_RADIUS + 5
    # Find a clear row that fits the residence/road/office row plus
    # the office's 2×2 extension and the distant mill.
    row_y = None
    for y in range(2, city.height - 3):
        clear = all(
            city.tile(x, y).building_id == -1
            and city.tile(x, y).terrain == CityTerrain.GRASS
            for x in list(range(1, 9)) + [1 + far]
        )
        ext = all(
            city.tile(x, y + 1).building_id == -1
            and city.tile(x, y + 1).terrain == CityTerrain.GRASS
            for x in range(7, 9)
        )
        if clear and ext:
            row_y = y
            break
    assert row_y is not None
    eng.submit(PlaceZone(x=1, y=row_y, kind=ZoneKind.RESIDENCE))
    for x in range(2, 7):
        eng.submit(PlaceZone(x=x, y=row_y, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=7, y=row_y, kind=ZoneKind.OFFICE))
    paint_adjacent_terrain(city, 1 + far, row_y, CityTerrain.FOREST)
    eng.submit(PlaceZone(x=1 + far, y=row_y, kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    for road in [b for b in city.buildings if b.kind == BuildingKind.ROAD]:
        road.completion = 1.0
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 3
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    # Seed plebs so labor.step actually staffs the office — the
    # cottage gate requires office coverage, which is zero when the
    # office has zero workers.
    city.districts[0].pops.plebs = 10.0
    eng.step(HOURS_PER_MONTH * 3)
    # Residence reaches at least cottages (or further) — the distant
    # mill imposes no cap.
    assert res.tier >= 2


# --- Satisfaction penalty ---------------------------------------------------

def test_apply_industrial_nuisance_subtracts_full_penalty_when_all_affected():
    """Single residence in single-residence district, mill in range
    → fraction is 1.0, full penalty lands."""
    _state, eng, city = _empty_city()
    res, mill = _designate_residence_road_office_and_industry(eng, city)
    assert mill is not None
    d = city.districts[0]
    d.satisfaction = 0.5
    _apply_industrial_nuisance(city)
    expected = 0.5 - INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH
    assert abs(d.satisfaction - expected) < 1e-6


def test_apply_industrial_nuisance_no_op_without_industry():
    _state, eng, city = _empty_city()
    res, _ = _designate_residence_road_office_and_industry(eng, city, with_mill=False)
    d = city.districts[0]
    d.satisfaction = 0.5
    _apply_industrial_nuisance(city)
    assert d.satisfaction == 0.5


def test_industrial_nuisance_tiles_includes_radius_around_mill():
    """The nuisance tile set should cover a (2*radius+1)² square
    centered on each industrial building, clipped to map bounds."""
    _state, eng, city = _empty_city()
    paint_adjacent_terrain(city, 10, 10, CityTerrain.FOREST)
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    tiles = _industrial_nuisance_tiles(city)
    assert (mill.x, mill.y) in tiles
    r = INDUSTRIAL_NUISANCE_RADIUS
    assert (mill.x + r, mill.y) in tiles
    assert (mill.x - r, mill.y) in tiles
    assert (mill.x, mill.y + r) in tiles
    # One past the radius is NOT included.
    assert (mill.x + r + 1, mill.y) not in tiles


def test_idle_industry_still_emits_nuisance():
    """The user said 'production buildings' — gating on completion,
    not on workers_assigned. An idle but completed mill still
    affects nearby residences."""
    _state, eng, city = _empty_city()
    paint_adjacent_terrain(city, 10, 10, CityTerrain.FOREST)
    eng.submit(PlaceZone(x=10, y=10, kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    mill.workers_assigned = 0  # idle
    tiles = _industrial_nuisance_tiles(city)
    assert (mill.x, mill.y) in tiles
