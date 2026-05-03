"""Industry — material production and workshop conversion.

Each tick:
  - Lumber mills produce timber proportional to assigned workers.
  - Quarries produce stone proportional to assigned workers.
  - Workshops consume input material (timber for furniture, stone for
    stoneware) and produce the finished good into the treasury,
    proportional to assigned workers.

Material production (mill/quarry) halts when the city's combined raw
materials (treasury.timber + treasury.stone) reach
total_storage_capacity. Workshops halt when the input pool can't
cover one tick's consumption — no partial production. Output goods
(furniture/stoneware) are uncapped for now since there's no consumer
in MVP."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import (
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
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
                if city.stored_materials() >= cap:
                    continue
                city.treasury.timber += (
                    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK * b.workers_assigned
                )
            elif b.kind == BuildingKind.QUARRY:
                if city.stored_materials() >= cap:
                    continue
                city.treasury.stone += (
                    QUARRY_STONE_PER_WORKER_PER_TICK * b.workers_assigned
                )
            elif b.kind == BuildingKind.WORKSHOP:
                _run_workshop(city, b)


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
