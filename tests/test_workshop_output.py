"""Tests for workshop output flowing through the warehouse cap pipeline.

Workshop production now lands in the city treasury (capped by the sum
of warehouse furniture / stoneware caps), spilling into the workshop's
own local buffer (WORKSHOP_OUTPUT_BUFFER) when the treasury is full.
Production halts entirely when both treasury and local buffer are full."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, SetWarehouseCaps, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    Good,
    WORKSHOP_INPUT_PER_WORKER_PER_TICK,
    WORKSHOP_OUTPUT_BUFFER,
    WORKSHOP_OUTPUT_PER_WORKER_PER_TICK,
)
from spqr.sim.systems import default_systems

from ._helpers import find_clear_grass


def _setup(*, with_warehouse: bool, furniture_cap: int = 60):
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 5_000.0  # plenty of input
    city.treasury.stone = 5_000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WORKSHOP))
    eng.step(1)
    workshop = next(b for b in city.buildings if b.kind == BuildingKind.WORKSHOP)
    workshop.completion = 1.0
    if with_warehouse:
        wh_xy = find_clear_grass(city, exclude={(spot[0], spot[1])})
        eng.submit(PlaceZone(x=wh_xy[0], y=wh_xy[1], kind=ZoneKind.WAREHOUSE))
        eng.step(1)
        warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
        warehouse.completion = 1.0
        # Re-allocate to dedicate furniture capacity.
        eng.submit(SetWarehouseCaps(
            warehouse.id, 0, 0, 0, furniture_cap, 300 - furniture_cap,
        ))
        eng.step(1)
    city.districts[0].pops.plebs = 50.0  # so labor staffs the workshop
    return state, eng, city, workshop


def test_workshop_output_lands_in_treasury_when_warehouse_capped():
    """With a warehouse providing furniture cap, workshop output goes
    into the city treasury (treasury.furniture grows; on-site buffer
    stays at 0 because there's plenty of treasury headroom)."""
    state, eng, city, workshop = _setup(with_warehouse=True, furniture_cap=200)
    workshop.good = int(Good.FURNITURE)
    eng.step(1)  # labor.step assigns workers
    treasury_before = city.treasury.furniture
    buffer_before = workshop.furniture_stored
    eng.step(50)
    assert city.treasury.furniture > treasury_before
    # No spillover yet; treasury cap (200) easily absorbs 50 ticks of output.
    assert workshop.furniture_stored == buffer_before


def test_workshop_output_spills_to_local_buffer_when_treasury_full():
    """Pre-fill treasury at the cap. Workshop output should land in the
    workshop's local buffer (up to WORKSHOP_OUTPUT_BUFFER) instead."""
    state, eng, city, workshop = _setup(with_warehouse=True, furniture_cap=60)
    workshop.good = int(Good.FURNITURE)
    eng.step(1)  # labor.step
    city.treasury.furniture = float(city.furniture_capacity())  # treasury full
    treasury_before = city.treasury.furniture
    buffer_before = workshop.furniture_stored
    eng.step(20)
    # Treasury didn't grow (was at cap).
    assert city.treasury.furniture <= treasury_before + 1e-6
    # Spillover landed in the local buffer.
    assert workshop.furniture_stored > buffer_before


def test_workshop_halts_when_treasury_and_buffer_both_full():
    """No furniture cap (no warehouse) AND local buffer at WORKSHOP_OUTPUT_BUFFER:
    production stops, no input consumed."""
    state, eng, city, workshop = _setup(with_warehouse=False)
    workshop.good = int(Good.FURNITURE)
    eng.step(1)
    workshop.furniture_stored = WORKSHOP_OUTPUT_BUFFER  # local buffer full
    timber_before = city.treasury.timber
    eng.step(20)
    # No input consumed because nowhere to put output.
    assert city.treasury.timber == timber_before
    assert workshop.furniture_stored == WORKSHOP_OUTPUT_BUFFER


def test_workshop_local_buffer_capped_at_workshop_output_buffer():
    """Even with sustained over-cap production, workshop.furniture_stored
    can't exceed WORKSHOP_OUTPUT_BUFFER."""
    state, eng, city, workshop = _setup(with_warehouse=False)
    workshop.good = int(Good.FURNITURE)
    eng.step(1)
    eng.step(HOURS_PER_MONTH)
    assert workshop.furniture_stored <= WORKSHOP_OUTPUT_BUFFER + 1e-6


def test_stoneware_workshop_uses_stoneware_cap_and_buffer():
    """Symmetric path for stoneware workshops — same cap/buffer
    mechanism, just on stoneware fields."""
    state, eng, city, workshop = _setup(with_warehouse=True, furniture_cap=0)
    # furniture_cap=0, stoneware_cap=300 from setup
    workshop.good = int(Good.STONEWARE)
    eng.step(1)
    assert city.stoneware_capacity() == 300
    treasury_before = city.treasury.stoneware
    eng.step(50)
    assert city.treasury.stoneware > treasury_before
