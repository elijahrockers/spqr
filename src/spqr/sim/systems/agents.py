"""Agent step — named citizens age and act on their roles.

MVP: magistrates simply age and may retire after a long tenure. Later
milestones add policy proposals, faction dynamics, succession, etc."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import HOURS_PER_YEAR, GameState
from spqr.sim.models import CitizenRole


# Years in office before a magistrate considers stepping down.
MAGISTRATE_TENURE_YEARS = 4


def step(state: GameState, rng: random.Random) -> None:
    yearly = (state.tick % HOURS_PER_YEAR) == 0 and state.tick > 0
    if not yearly:
        return
    for city in state.cities:
        survivors: list = []
        for c in city.citizens:
            c.age += 1
            # Old age mortality bites past 60.
            mortality = 0.01 if c.age < 60 else 0.05 + 0.01 * (c.age - 60)
            if rng.random() < mortality:
                push_log(
                    state.log,
                    state.tick,
                    LogSeverity.INFO,
                    f"{c.name} ({c.role.name.title()}) has died at age {c.age}.",
                )
                continue
            if c.role == CitizenRole.MAGISTRATE:
                tenure_hours = state.tick - c.role_since_tick
                if tenure_hours >= MAGISTRATE_TENURE_YEARS * HOURS_PER_YEAR:
                    push_log(
                        state.log,
                        state.tick,
                        LogSeverity.INFO,
                        f"Magistrate {c.name} retires after a long tenure.",
                    )
                    # Retirement only — successor selection lands in a later milestone.
                    continue
            survivors.append(c)
        city.citizens = survivors
