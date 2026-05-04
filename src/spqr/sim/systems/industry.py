"""Industry — material production and workshop conversion.

Each tick:
  - Lumber mills produce timber proportional to assigned workers.
    Output lands in the treasury first (capped by warehouse + forum
    storage). When the treasury is at its cap, the spillover lands
    in the producing mill's local buffer, up to
    LUMBER_MILL_TIMBER_BUFFER. The mill stops producing only when
    both the treasury and the local buffer are full.
  - Quarries: same model with stone, capped at QUARRY_STONE_BUFFER.
  - Workshops consume input material (timber for furniture, stone
    for stoneware) and produce the finished good into the treasury,
    proportional to assigned workers. Workshops draw from the
    treasury only — they don't reach into mill/quarry local buffers.

Material production halts when nowhere can absorb the new output.
Workshops halt when the input pool can't cover one tick's
consumption — no partial production. Output goods
(furniture/stoneware) are uncapped for now since there's no consumer
in MVP."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import (
    LUMBER_MILL_TIMBER_BUFFER,
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_BUFFER,
    QUARRY_STONE_PER_WORKER_PER_TICK,
    WORKSHOP_INPUT_PER_WORKER_PER_TICK,
    WORKSHOP_OUTPUT_PER_WORKER_PER_TICK,
    BuildingKind,
    Good,
)


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        cap = city.total_storage_capacity()
        for b in city.buildings:
            if b.is_under_construction or b.workers_assigned <= 0:
                continue
            if b.kind == BuildingKind.LUMBER_MILL:
                produced = (
                    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK * b.workers_assigned
                )
                _deposit_material(
                    city, b, produced,
                    treasury_attr="timber",
                    buffer_attr="timber_stored",
                    buffer_cap=LUMBER_MILL_TIMBER_BUFFER,
                    treasury_cap=cap,
                )
            elif b.kind == BuildingKind.QUARRY:
                produced = (
                    QUARRY_STONE_PER_WORKER_PER_TICK * b.workers_assigned
                )
                _deposit_material(
                    city, b, produced,
                    treasury_attr="stone",
                    buffer_attr="stone_stored",
                    buffer_cap=QUARRY_STONE_BUFFER,
                    treasury_cap=cap,
                )
            elif b.kind == BuildingKind.WORKSHOP:
                _run_workshop(city, b)


def _deposit_material(
    city,  # type: ignore[no-untyped-def]
    b,  # type: ignore[no-untyped-def]
    amount: float,
    *,
    treasury_attr: str,
    buffer_attr: str,
    buffer_cap: float,
    treasury_cap: int,
) -> None:
    """Land `amount` of newly-produced material first in the city
    treasury (up to `treasury_cap`), then spill any leftover into the
    producing building's local buffer (up to `buffer_cap`). Anything
    that doesn't fit either pool is discarded — production stalled
    for the rest of the tick."""
    if amount <= 0:
        return
    headroom = max(0.0, treasury_cap - city.stored_materials())
    to_treasury = min(amount, headroom)
    if to_treasury > 0:
        setattr(
            city.treasury, treasury_attr,
            getattr(city.treasury, treasury_attr) + to_treasury,
        )
        amount -= to_treasury
    if amount <= 0:
        return
    buffer_left = max(0.0, buffer_cap - getattr(b, buffer_attr))
    to_buffer = min(amount, buffer_left)
    if to_buffer > 0:
        setattr(b, buffer_attr, getattr(b, buffer_attr) + to_buffer)


def _run_workshop(city, b) -> None:  # type: ignore[no-untyped-def]
    """Convert input material → output good for one tick. No-op if the
    treasury can't fully cover this tick's input (no partial yields)."""
    input_needed = WORKSHOP_INPUT_PER_WORKER_PER_TICK * b.workers_assigned
    output_made = WORKSHOP_OUTPUT_PER_WORKER_PER_TICK * b.workers_assigned
    if b.good == int(Good.FURNITURE):
        if city.treasury.timber < input_needed:
            return
        city.treasury.timber -= input_needed
        city.treasury.furniture += output_made
    elif b.good == int(Good.STONEWARE):
        if city.treasury.stone < input_needed:
            return
        city.treasury.stone -= input_needed
        city.treasury.stoneware += output_made
