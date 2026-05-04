"""Labor allocation — fills builder slots on construction sites and worker
slots on operational buildings from the same district workforce. Runs each
tick to reflect zone changes and completions immediately.

Allocation is bucketed by LaborCategory and drained in the city's
`labor_priority` order. Within a bucket, placement order
(`district.building_ids`) is preserved, so older buildings in the same
category still get workers first; flipping priority lets the player
decide whether construction, food, raw materials, finished goods, or
admin gets the first cut of each district's workforce. With a fixed
workforce, designating many sites at once will spread builders thin and
slow each site proportionally — but only after higher-priority buckets
are satisfied."""

from __future__ import annotations

import random

from spqr.engine.world import GameState
from spqr.sim.models import (
    BUILDER_SLOTS,
    LaborCategory,
    labor_category_for,
)


_NUM_CATEGORIES = len(LaborCategory)


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        for district in city.districts:
            available = int(district.pops.workers())
            buckets: list[list] = [[] for _ in range(_NUM_CATEGORIES)]
            for b_id in district.building_ids:
                b = city.buildings[b_id]
                cat = labor_category_for(b)
                if cat is None:
                    # Buildings without a worker bucket (residences,
                    # storage, civic) stay at zero — same as today.
                    b.workers_assigned = 0
                    continue
                buckets[int(cat)].append(b)
            for cat_value in city.labor_priority:
                if not 0 <= cat_value < _NUM_CATEGORIES:
                    continue
                for b in buckets[cat_value]:
                    if b.is_under_construction:
                        slots = BUILDER_SLOTS.get(b.kind, 1)
                    else:
                        slots = b.operational_worker_slots()
                    if slots == 0:
                        b.workers_assigned = 0
                        continue
                    want = min(slots, max(0, available))
                    b.workers_assigned = want
                    available -= want
            # Defensive: if the priority list omits any bucket (the
            # SetLaborPriority validator should prevent this, but
            # corrupt saves could slip through), zero those buildings.
            seen = {c for c in city.labor_priority if 0 <= c < _NUM_CATEGORIES}
            for cat_value in range(_NUM_CATEGORIES):
                if cat_value in seen:
                    continue
                for b in buckets[cat_value]:
                    b.workers_assigned = 0
