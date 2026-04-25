"""Military — slow training advancement and (eventual) recruitment.

For MVP this is mostly a passive system: garrison training drifts toward 1.0
when housed in barracks, and drifts down when the treasury can't pay them.
Recruitment from the pop pool is left for a follow-up milestone."""

from __future__ import annotations

import random

from spqr.engine.world import HOURS_PER_DAY, GameState
from spqr.sim.models import BuildingKind


def step(state: GameState, rng: random.Random) -> None:
    daily = (state.tick % HOURS_PER_DAY) == 0 and state.tick > 0
    if not daily:
        return
    for city in state.cities:
        # Garrison training advances if there's at least one barracks built.
        has_barracks = any(
            b.kind == BuildingKind.BARRACKS and b.completion >= 1.0
            for b in city.buildings
        )
        if has_barracks and city.garrison.legionaries > 0:
            city.garrison.training = min(1.0, city.garrison.training + 0.005)
        else:
            city.garrison.training = max(0.0, city.garrison.training - 0.002)
