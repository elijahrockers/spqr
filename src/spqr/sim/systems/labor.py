"""Labor allocation — fills builder slots on construction sites and worker
slots on operational buildings from the same district workforce. Runs each
tick to reflect zone changes and completions immediately.

Allocation order is `district.building_ids` (placement order). Older
buildings get workers first; new construction sites compete for whatever
remains. With a fixed workforce, designating many sites at once will
spread builders thin and slow each site proportionally."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import BUILDER_SLOTS, operational_worker_slots


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        for district in city.districts:
            available = int(district.pops.workers())
            for b_id in district.building_ids:
                b = city.buildings[b_id]
                if b.completion < 1.0:
                    slots = BUILDER_SLOTS.get(b.kind, 1)
                else:
                    slots = operational_worker_slots(b)
                if slots == 0:
                    b.workers_assigned = 0
                    continue
                want = min(slots, max(0, available))
                b.workers_assigned = want
                available -= want
