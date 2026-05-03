"""Construction system — advances completion based on assigned builders.

Each tick a building under construction gains
    workers_assigned / BUILD_HOURS[kind]
of progress. With full builder allocation, smaller civic builds finish in
~7 game days, larger ones in 3-5 weeks. With zero builders assigned (no
spare workforce), construction stalls completely until labor frees up."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState
from spqr.sim.models import BUILD_HOURS


def step(state: GameState, rng: random.Random) -> None:
    for city in state.cities:
        for b in city.buildings:
            if b.is_completed:
                continue
            if b.workers_assigned <= 0:
                continue  # stalled — no labor available this tick
            denom = BUILD_HOURS.get(b.kind, 168)
            b.completion = min(1.0, b.completion + b.workers_assigned / denom)
            if b.is_completed:
                push_log(
                    state.log,
                    state.tick,
                    LogSeverity.GOOD,
                    f"{b.kind.name.title()} at ({b.x},{b.y}) completed.",
                )
