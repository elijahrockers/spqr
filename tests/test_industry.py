"""Tests for the lumber mill + quarry pipeline. Both produce material
into the city treasury, capped at total_storage_capacity (forum +
warehouse). Lumber mills don't need timber to build (so the player can
bootstrap from starter materials); quarries do."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BUILDING_COST,
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_PER_WORKER_PER_TICK,
    BuildingKind,
)
from spqr.sim.systems import default_systems

from ._helpers import find_clear_grass


def _designate_and_finish(eng, city, kind: ZoneKind, plebs: float = 50.0):
    """Designate one mill or quarry, hand-finish it, and seed labor.
    Caller is responsible for treasury — this helper only pays the
    designation cost; it does NOT reset stocks afterward."""
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=kind))
    eng.step(1)
    b = next(
        bx for bx in city.buildings
        if bx.kind == BuildingKind.LUMBER_MILL or bx.kind == BuildingKind.QUARRY
    )
    b.completion = 1.0
    city.districts[0].pops.plebs = plebs
    return b


def test_lumber_mill_costs_no_timber():
    """The bootstrap-friendly invariant: a lumber mill can be built
    even when the city has zero timber."""
    cost = BUILDING_COST[BuildingKind.LUMBER_MILL]
    assert cost.timber == 0


def test_quarry_costs_timber():
    """The pacing invariant: quarries need timber, so the player has
    to build a lumber mill first (or use starter timber)."""
    cost = BUILDING_COST[BuildingKind.QUARRY]
    assert cost.timber > 0


def test_lumber_mill_produces_timber_when_workers_assigned():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Build a warehouse so total_storage_capacity > 0 (forum absent on
    # a fresh-start city), and a lumber mill alongside it.
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    mill = _designate_and_finish(eng, city, ZoneKind.LUMBER_MILL)
    # Now drop treasury so production has headroom under the cap (250).
    city.treasury.timber = 0.0
    city.treasury.stone = 0.0
    eng.step(50)
    assert mill.workers_assigned > 0
    expected_min = LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK * mill.workers_assigned * 50 * 0.95
    assert city.treasury.timber >= expected_min


def test_quarry_produces_stone_when_workers_assigned():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    quarry = _designate_and_finish(eng, city, ZoneKind.QUARRY)
    city.treasury.timber = 0.0
    city.treasury.stone = 0.0
    eng.step(50)
    assert quarry.workers_assigned > 0
    expected_min = QUARRY_STONE_PER_WORKER_PER_TICK * quarry.workers_assigned * 50 * 0.95
    assert city.treasury.stone >= expected_min


def test_industry_halts_when_at_storage_cap():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # No forum / warehouse → cap is 0. Mill should produce nothing
    # because starter timber (80) + stone (40) is already over cap.
    city.treasury.denarii = 10_000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    city.districts[0].pops.plebs = 50.0
    cap = city.total_storage_capacity()
    assert cap == 0
    assert city.treasury.timber + city.treasury.stone >= cap
    timber_before = city.treasury.timber
    eng.step(50)
    assert city.treasury.timber == timber_before


def test_industry_resumes_after_warehouse_unblocks_cap():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    mill = _designate_and_finish(eng, city, ZoneKind.LUMBER_MILL)
    # Starter treasury (80t + 40s = 120) > cap (0) → mill halted.
    timber_before = city.treasury.timber
    eng.step(20)
    assert city.treasury.timber == timber_before
    # Build a warehouse — cap jumps to 250. Spend down materials to
    # make headroom under the new cap, then production resumes.
    spot = find_clear_grass(city)
    city.treasury.timber = 100.0  # afford warehouse cost (20t)
    city.treasury.stone = 100.0
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    city.treasury.timber = 0.0
    city.treasury.stone = 0.0
    eng.step(50)
    assert mill.workers_assigned > 0
    assert city.treasury.timber > 0.0
