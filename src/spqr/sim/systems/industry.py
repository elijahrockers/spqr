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
