"""Tests for the per-warehouse capacity split feature.

Each warehouse has WAREHOUSE_TOTAL_CAPACITY (300) units split across
five goods: timber, stone, vegetables, furniture, stoneware. The split
is configurable via SetWarehouseCaps; defaults are uniform (60 each).
Material caps (timber, stone) and finished-goods caps (furniture,
stoneware) sum into the city-wide treasury cap (industry halts at
limits); vegetables stays per-warehouse (transport halts at the
warehouse's own veg cap)."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, SetWarehouseCaps, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    FORUM_STONE_CAPACITY,
    FORUM_TIMBER_CAPACITY,
    LUMBER_MILL_TIMBER_BUFFER,
    WAREHOUSE_DEFAULT_CAP_FURNITURE,
    WAREHOUSE_DEFAULT_CAP_STONE,
    WAREHOUSE_DEFAULT_CAP_STONEWARE,
    WAREHOUSE_DEFAULT_CAP_TIMBER,
    WAREHOUSE_DEFAULT_CAP_VEGETABLES,
    WAREHOUSE_TOTAL_CAPACITY,
)
from spqr.sim.systems import default_systems

from ._helpers import bootstrap_starter_city, find_clear_grass


def _place_warehouse(eng, city) -> int:
    """Place + hand-complete a warehouse on the first clear grass.
    Returns its building_id."""
    spot = find_clear_grass(city)
    city.treasury.denarii = max(city.treasury.denarii, 10_000.0)
    city.treasury.timber = max(city.treasury.timber, 1_000.0)
    city.treasury.stone = max(city.treasury.stone, 1_000.0)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    w = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    w.completion = 1.0
    return w.id


def test_warehouse_total_capacity_is_300():
    """The headline number — 300 split across five goods."""
    assert WAREHOUSE_TOTAL_CAPACITY == 300


def test_default_split_is_uniform():
    """Sanity: defaults distribute the full 300 evenly across the
    five goods so a freshly-designated warehouse handles a bit of
    everything without configuration."""
    assert WAREHOUSE_DEFAULT_CAP_TIMBER == 60
    assert WAREHOUSE_DEFAULT_CAP_STONE == 60
    assert WAREHOUSE_DEFAULT_CAP_VEGETABLES == 60
    assert WAREHOUSE_DEFAULT_CAP_FURNITURE == 60
    assert WAREHOUSE_DEFAULT_CAP_STONEWARE == 60
    assert (
        WAREHOUSE_DEFAULT_CAP_TIMBER
        + WAREHOUSE_DEFAULT_CAP_STONE
        + WAREHOUSE_DEFAULT_CAP_VEGETABLES
        + WAREHOUSE_DEFAULT_CAP_FURNITURE
        + WAREHOUSE_DEFAULT_CAP_STONEWARE
        == WAREHOUSE_TOTAL_CAPACITY
    )


def test_new_warehouse_uses_default_caps():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    w = city.buildings[w_id]
    assert w.warehouse_cap_timber == WAREHOUSE_DEFAULT_CAP_TIMBER
    assert w.warehouse_cap_stone == WAREHOUSE_DEFAULT_CAP_STONE
    assert w.warehouse_cap_vegetables == WAREHOUSE_DEFAULT_CAP_VEGETABLES
    assert w.warehouse_cap_furniture == WAREHOUSE_DEFAULT_CAP_FURNITURE
    assert w.warehouse_cap_stoneware == WAREHOUSE_DEFAULT_CAP_STONEWARE


def test_set_warehouse_caps_applies_valid_split():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    eng.submit(SetWarehouseCaps(w_id, 150, 50, 50, 25, 25))
    eng.step(1)
    w = city.buildings[w_id]
    assert (
        w.warehouse_cap_timber,
        w.warehouse_cap_stone,
        w.warehouse_cap_vegetables,
        w.warehouse_cap_furniture,
        w.warehouse_cap_stoneware,
    ) == (150, 50, 50, 25, 25)


def test_set_warehouse_caps_rejects_oversized_sum():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    # Sum 100×5 = 500 > 300; must be rejected wholesale.
    eng.submit(SetWarehouseCaps(w_id, 100, 100, 100, 100, 100))
    eng.step(1)
    w = city.buildings[w_id]
    assert w.warehouse_cap_timber == WAREHOUSE_DEFAULT_CAP_TIMBER
    assert w.warehouse_cap_stone == WAREHOUSE_DEFAULT_CAP_STONE
    assert w.warehouse_cap_vegetables == WAREHOUSE_DEFAULT_CAP_VEGETABLES
    assert w.warehouse_cap_furniture == WAREHOUSE_DEFAULT_CAP_FURNITURE
    assert w.warehouse_cap_stoneware == WAREHOUSE_DEFAULT_CAP_STONEWARE


def test_set_warehouse_caps_rejects_negatives():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    eng.submit(SetWarehouseCaps(w_id, 60, 60, -1, 60, 60))
    eng.step(1)
    w = city.buildings[w_id]
    assert w.warehouse_cap_vegetables == WAREHOUSE_DEFAULT_CAP_VEGETABLES


def test_set_warehouse_caps_no_op_for_non_warehouse():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    eng.submit(SetWarehouseCaps(farm.id, 100, 50, 50, 50, 50))
    eng.step(1)
    assert farm.warehouse_cap_timber == WAREHOUSE_DEFAULT_CAP_TIMBER
    assert farm.warehouse_cap_stone == WAREHOUSE_DEFAULT_CAP_STONE
    assert farm.warehouse_cap_vegetables == WAREHOUSE_DEFAULT_CAP_VEGETABLES
    assert farm.warehouse_cap_furniture == WAREHOUSE_DEFAULT_CAP_FURNITURE
    assert farm.warehouse_cap_stoneware == WAREHOUSE_DEFAULT_CAP_STONEWARE


def test_city_timber_capacity_sums_warehouse_allocations():
    """Each warehouse contributes its `warehouse_cap_timber` to the
    city's timber cap — that's what industry checks against."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_a = _place_warehouse(eng, city)
    # Reconfigure A to all-timber.
    eng.submit(SetWarehouseCaps(w_a, 300, 0, 0, 0, 0))
    eng.step(1)
    assert city.timber_capacity() == 300
    assert city.stone_capacity() == 0
    assert city.furniture_capacity() == 0
    assert city.stoneware_capacity() == 0
    # No forum, so totals come from the warehouse alone.
    assert city.total_storage_capacity() == 300


def test_city_furniture_and_stoneware_capacity_sums_warehouse_allocations():
    """Workshop output goes through the same per-warehouse cap pipeline
    as materials. Confirm furniture_capacity / stoneware_capacity
    aggregate the same way."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    eng.submit(SetWarehouseCaps(w_id, 0, 0, 0, 200, 100))
    eng.step(1)
    assert city.furniture_capacity() == 200
    assert city.stoneware_capacity() == 100


def test_warehouse_cap_zero_for_a_good_means_no_storage_for_that_good():
    """Setting cap_vegetables=0 makes the warehouse refuse new
    vegetables transport — but doesn't strip already-stored stock
    (gentle override; lets a player drain inventory)."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    w = city.buildings[w_id]
    w.vegetables_stored = 50.0  # pre-seed before reconfig
    eng.submit(SetWarehouseCaps(w_id, 100, 100, 0, 50, 50))
    eng.step(1)
    # Existing stock preserved despite being over the new cap.
    assert w.vegetables_stored == 50.0
    assert w.warehouse_cap_vegetables == 0


def test_timber_cap_halts_mill_production_at_treasury_full():
    """Industry should stop adding timber to the treasury once
    treasury.timber reaches city.timber_capacity(). Subsequent output
    spills into the mill's local buffer up to LUMBER_MILL_TIMBER_BUFFER,
    but the treasury cap holds firm."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Place a warehouse with all-timber cap so timber_capacity() is well-
    # defined and stone_capacity() is 0.
    w_id = _place_warehouse(eng, city)
    eng.submit(SetWarehouseCaps(w_id, 300, 0, 0, 0, 0))
    eng.step(1)
    # Place a lumber mill near a forest patch.
    mill_xy = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id != -1 or t.terrain != CityTerrain.GRASS:
                continue
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if not city.in_bounds(nx, ny):
                    continue
                if city.tile(nx, ny).terrain == CityTerrain.FOREST:
                    mill_xy = (x, y)
                    break
            if mill_xy:
                break
        if mill_xy:
            break
    if mill_xy is None:
        spot = find_clear_grass(city)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = spot[0] + dx, spot[1] + dy
            if city.in_bounds(nx, ny) and city.tile(nx, ny).building_id == -1:
                city.tile(nx, ny).terrain = CityTerrain.FOREST
                mill_xy = spot
                break
    assert mill_xy is not None
    eng.submit(PlaceZone(x=mill_xy[0], y=mill_xy[1], kind=ZoneKind.LUMBER_MILL))
    eng.step(1)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    mill.completion = 1.0
    city.treasury.timber = float(city.timber_capacity())
    city.districts[0].pops.plebs = 50.0
    eng.step(HOURS_PER_MONTH)
    assert city.treasury.timber <= float(city.timber_capacity()) + 1e-6
    assert mill.timber_stored <= LUMBER_MILL_TIMBER_BUFFER + 1e-6


def test_set_warehouse_caps_idempotent_no_op_when_unchanged():
    """Submitting the current values again is a no-op (no log churn,
    no redundant state writes)."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    w_id = _place_warehouse(eng, city)
    log_before = len(state.log)
    eng.submit(SetWarehouseCaps(w_id, 60, 60, 60, 60, 60))
    eng.step(1)
    assert len(state.log) == log_before


def test_forum_constants_are_split():
    """Sanity check on the forum's per-material contribution."""
    assert FORUM_TIMBER_CAPACITY + FORUM_STONE_CAPACITY == 100
