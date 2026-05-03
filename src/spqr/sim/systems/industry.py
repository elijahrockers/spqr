"""Industry — material production from lumber mills and quarries.

Each tick:
  - Lumber mills produce timber proportional to assigned workers.
  - Quarries produce stone proportional to assigned workers.

Production halts when the city's combined materials
(treasury.timber + treasury.stone) reaches total_storage_capacity
(forum + warehouses). This is what "yields stored in warehouse" means
in practice — without enough warehouse storage, production stops.

Workshop and forum slots are out of scope here; those buildings have
operational worker slots but no production hook in MVP yet."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import (
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_PER_WORKER_PER_TICK,
    BuildingKind,
    City,
)


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        cap = _total_storage_capacity(city)
        for b in city.buildings:
            if b.completion < 1.0 or b.workers_assigned <= 0:
                continue
            if b.kind == BuildingKind.LUMBER_MILL:
                if city.treasury.timber + city.treasury.stone >= cap:
                    continue
                city.treasury.timber += (
                    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK * b.workers_assigned
                )
            elif b.kind == BuildingKind.QUARRY:
                if city.treasury.timber + city.treasury.stone >= cap:
                    continue
                city.treasury.stone += (
                    QUARRY_STONE_PER_WORKER_PER_TICK * b.workers_assigned
                )


def _total_storage_capacity(city: City) -> int:
    """Local copy to avoid the engine.tick → systems import cycle. Same
    formula: sum STORAGE_CAPACITY across completed storage-bearing
    buildings (forum, warehouse)."""
    from spqr.sim.models import STORAGE_CAPACITY

    cap = 0
    for b in city.buildings:
        if b.completion < 1.0:
            continue
        cap += STORAGE_CAPACITY.get(b.kind, 0)
    return cap
