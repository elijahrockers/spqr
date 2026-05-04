"""Tests for the local material buffer on lumber mills / quarries.

When the city treasury can't accept new timber (storage cap full),
a lumber mill spills production into its own `timber_stored` buffer
up to LUMBER_MILL_TIMBER_BUFFER. Construction `pay_cost` drains
that buffer when the treasury alone can't cover the bill. Same
pattern for quarries with stone."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BUILDING_COST,
    LUMBER_MILL_TIMBER_BUFFER,
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_BUFFER,
    BuildingKind,
    CityTerrain,
)
from spqr.sim.systems import default_systems

from ._helpers import (
    find_clear_grass,
    find_clear_grass_adjacent_to,
)


def _city_with_completed_mill(plebs: float = 50.0):
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    spot = find_clear_grass_adjacent_to(city, {CityTerrain.FOREST})
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    city.districts[0].pops.plebs = plebs
    return state, eng, city, mill


def test_mill_buffer_fills_when_treasury_at_cap():
    """No warehouse / forum → cap=0. Starter timber+stone are over
    the cap, so production routes to the mill's local buffer
    instead of being dropped on the floor."""
    state, eng, city, mill = _city_with_completed_mill()
    # Starter treasury (80t + 40s = 120) > cap (0).
    assert city.total_storage_capacity() == 0
    eng.step(50)
    assert mill.workers_assigned > 0
    # Buffer grew by ~1 worker × rate × ticks. Allow some slack for
    # the first labor-allocation tick.
    expected_min = (
        LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK
        * mill.workers_assigned * 50 * 0.95
    )
    assert mill.timber_stored >= expected_min


def test_mill_buffer_caps_at_buffer_size():
    """Once the buffer reaches LUMBER_MILL_TIMBER_BUFFER, further
    production stops landing anywhere — no infinite stockpile."""
    state, eng, city, mill = _city_with_completed_mill(plebs=50.0)
    # Run long enough that production would massively overflow.
    eng.step(2000)
    assert mill.timber_stored <= LUMBER_MILL_TIMBER_BUFFER + 1e-6
    # And it should be at the cap, not somewhere mid-buffer.
    assert mill.timber_stored >= LUMBER_MILL_TIMBER_BUFFER - 1e-6


def test_construction_pays_from_mill_buffer_when_treasury_empty():
    """A road costs 5d + 2s. With treasury timber/stone at zero but
    mill buffer holding stock, paying for construction should drain
    the buffer (well, the relevant resource — road needs stone, not
    timber, so use a residence designation that costs nothing
    material; actually use a workshop designation which costs
    timber+stone)."""
    state, eng, city, mill = _city_with_completed_mill()
    # Fill the mill buffer.
    mill.timber_stored = LUMBER_MILL_TIMBER_BUFFER
    # Drain treasury timber to zero so the buffer is the only source.
    city.treasury.timber = 0.0
    cost = BUILDING_COST[BuildingKind.WORKSHOP]
    timber_needed = cost.timber
    assert timber_needed > 0
    # available_timber should reflect the buffer.
    assert city.available_timber() == LUMBER_MILL_TIMBER_BUFFER
    # Pay-cost drains the buffer (treasury covers the stone /
    # denarii portions from the seeded reserves).
    city.treasury.denarii = 1_000.0
    city.treasury.stone = 100.0
    assert city.can_afford(cost)
    city.pay_cost(cost)
    assert mill.timber_stored == LUMBER_MILL_TIMBER_BUFFER - timber_needed


def test_quarry_buffer_fills_with_stone():
    """Symmetric to the mill case, just with stone."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    spot = find_clear_grass_adjacent_to(
        city, {CityTerrain.HILL, CityTerrain.ROCK},
    )
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.QUARRY))
    eng.step(1)
    quarry = next(b for b in city.buildings if b.kind == BuildingKind.QUARRY)
    quarry.completion = 1.0
    city.districts[0].pops.plebs = 50.0
    eng.step(50)
    assert quarry.workers_assigned > 0
    assert quarry.stone_stored > 0
    assert quarry.stone_stored <= QUARRY_STONE_BUFFER + 1e-6


def test_can_afford_uses_combined_pool():
    """A construction cost that needs more timber than the treasury
    has alone should still be affordable when the difference sits
    in a mill buffer."""
    state, eng, city, mill = _city_with_completed_mill()
    city.treasury.timber = 0.0
    mill.timber_stored = 30.0
    # Workshop cost is 60d + 15t + 10s.
    cost = BUILDING_COST[BuildingKind.WORKSHOP]
    city.treasury.denarii = 1_000.0
    city.treasury.stone = 100.0
    assert city.available_timber() == 30.0
    assert city.can_afford(cost)
    # If both treasury and buffer are empty, can't afford.
    mill.timber_stored = 0.0
    assert not city.can_afford(cost)


def test_pay_cost_drains_treasury_before_buffer():
    """Treasury is the primary pool; buffer is the fallback. A
    payment should drain treasury first, only touching the buffer
    for the shortfall."""
    state, eng, city, mill = _city_with_completed_mill()
    city.treasury.denarii = 1_000.0
    city.treasury.timber = 10.0
    city.treasury.stone = 100.0
    mill.timber_stored = 50.0
    cost = BUILDING_COST[BuildingKind.WORKSHOP]  # 15 timber needed
    city.pay_cost(cost)
    # Treasury timber went to 0 (covered 10 of 15).
    assert city.treasury.timber == 0.0
    # Buffer covered the remaining 5.
    assert mill.timber_stored == 45.0
