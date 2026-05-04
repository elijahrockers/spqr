"""Industry — material production and workshop conversion.

Each tick:
  - Lumber mills produce timber proportional to assigned workers.
    Output lands in the treasury first (capped by city.timber_capacity,
    the sum of every warehouse's per-material allocation plus the
    forum's fixed timber share). When the treasury is at its timber
    cap, the spillover lands in the producing mill's local buffer, up
    to LUMBER_MILL_TIMBER_BUFFER. The mill stops producing only when
    both the treasury and the local buffer are full.
  - Quarries: same model with stone, against city.stone_capacity and
    capped per-quarry at QUARRY_STONE_BUFFER.
  - Workshops consume input material (timber for furniture, stone
    for stoneware) and produce the finished good through the same
    deposit pipeline as mills/quarries: into the treasury first
    (capped by city.furniture_capacity / city.stoneware_capacity from
    warehouses), then spillover into the workshop's local buffer
    (WORKSHOP_OUTPUT_BUFFER). Production halts when both treasury
    and local buffer are full.

Material production halts when nowhere can absorb the new output.
Workshops halt when the input pool can't cover one tick's
consumption — no partial production."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import (
    LUMBER_MILL_TIMBER_BUFFER,
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_BUFFER,
    QUARRY_STONE_PER_WORKER_PER_TICK,
    WORKSHOP_INPUT_PER_WORKER_PER_TICK,
    WORKSHOP_OUTPUT_BUFFER,
    WORKSHOP_OUTPUT_PER_WORKER_PER_TICK,
    BuildingKind,
    Good,
)


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        timber_cap = city.timber_capacity()
        stone_cap = city.stone_capacity()
        furniture_cap = city.furniture_capacity()
        stoneware_cap = city.stoneware_capacity()
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
                    treasury_cap=timber_cap,
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
                    treasury_cap=stone_cap,
                )
            elif b.kind == BuildingKind.WORKSHOP:
                _run_workshop(
                    city, b, furniture_cap=furniture_cap,
                    stoneware_cap=stoneware_cap,
                )


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
    treasury (up to `treasury_cap` for THIS material — caller passes
    the per-material cap), then spill any leftover into the producing
    building's local buffer (up to `buffer_cap`). Anything that doesn't
    fit either pool is discarded — production stalled for the rest of
    the tick."""
    if amount <= 0:
        return
    current = getattr(city.treasury, treasury_attr)
    headroom = max(0.0, treasury_cap - current)
    to_treasury = min(amount, headroom)
    if to_treasury > 0:
        setattr(city.treasury, treasury_attr, current + to_treasury)
        amount -= to_treasury
    if amount <= 0:
        return
    buffer_left = max(0.0, buffer_cap - getattr(b, buffer_attr))
    to_buffer = min(amount, buffer_left)
    if to_buffer > 0:
        setattr(b, buffer_attr, getattr(b, buffer_attr) + to_buffer)


def _run_workshop(  # type: ignore[no-untyped-def]
    city, b, *, furniture_cap: int, stoneware_cap: int,
) -> None:
    """Convert input material → output good for one tick. Pre-checks:
    the treasury must hold one tick's input AND there must be somewhere
    to put the output (treasury under cap OR local buffer under
    WORKSHOP_OUTPUT_BUFFER). If both checks pass, the input is consumed
    and the output flows through the same deposit pipeline mills /
    quarries use, so the workshop's local buffer naturally fills as a
    spillover when warehouses are full."""
    input_needed = WORKSHOP_INPUT_PER_WORKER_PER_TICK * b.workers_assigned
    output_made = WORKSHOP_OUTPUT_PER_WORKER_PER_TICK * b.workers_assigned
    if b.good == int(Good.FURNITURE):
        input_attr = "timber"
        output_treasury_attr = "furniture"
        output_buffer_attr = "furniture_stored"
        output_cap = furniture_cap
    elif b.good == int(Good.STONEWARE):
        input_attr = "stone"
        output_treasury_attr = "stoneware"
        output_buffer_attr = "stoneware_stored"
        output_cap = stoneware_cap
    else:
        return
    if getattr(city.treasury, input_attr) < input_needed:
        return
    # If neither the treasury nor the workshop's local buffer can
    # absorb this tick's output, halt — don't burn input that yields
    # nothing storable.
    treasury_headroom = max(
        0.0, output_cap - getattr(city.treasury, output_treasury_attr)
    )
    buffer_headroom = max(
        0.0, WORKSHOP_OUTPUT_BUFFER - getattr(b, output_buffer_attr)
    )
    if treasury_headroom + buffer_headroom < output_made:
        # Partial-fit allowed: workshop produces what fits. (Same
        # behavior as mills/quarries — the spillover is per-tick, not
        # all-or-nothing for the WHOLE tick's output.) But if NOTHING
        # fits, no production this tick.
        if treasury_headroom + buffer_headroom <= 0.0:
            return
    setattr(city.treasury, input_attr, getattr(city.treasury, input_attr) - input_needed)
    _deposit_material(
        city, b, output_made,
        treasury_attr=output_treasury_attr,
        buffer_attr=output_buffer_attr,
        buffer_cap=WORKSHOP_OUTPUT_BUFFER,
        treasury_cap=output_cap,
    )
