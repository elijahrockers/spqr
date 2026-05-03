"""Demographics — weekly migration waves, monthly births/deaths/unrest.

Migration runs on every weekly boundary so settlers arrive in visible
waves; rate is gated on housing capacity (tier-aware via residence_capacity)
and satisfaction. Births, deaths, and unrest decay run on the slower
monthly cadence (biological rates). Both gates are early-returned so
the function is a cheap nop on most ticks."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import (
    GameState,
    is_first_of_month,
    is_first_of_week,
)
from spqr.sim.models import BuildingKind


# Monthly base rates (per individual). Tuned for slow but visible growth.
PLEB_BIRTH_RATE = 0.012
PLEB_DEATH_RATE = 0.006
PATRICIAN_BIRTH_RATE = 0.008
PATRICIAN_DEATH_RATE = 0.005

# Plebs/week migration ceiling at sat=1.0 per district. Scales linearly
# with satisfaction above the 0.3 floor.
MIGRATION_BASE_RATE = 5.0

# Outflow per week when overfilled or unhappy. Approximates the prior
# monthly 5% rate spread over four weeks so a starving district drains
# at roughly the same long-run pace.
WEEKLY_OUTFLOW_RATE = 0.0125


def step(state: GameState, rng: random.Random) -> None:
    weekly = is_first_of_week(state.tick)
    monthly = is_first_of_month(state.tick)
    if not weekly and not monthly:
        return
    for city in state.cities:
        for d in city.districts:
            sat = d.satisfaction
            unrest = d.pops.unrest

            if monthly:
                sat_birth_mod = 0.5 + 1.0 * sat   # 0.5x at sat=0, 1.5x at sat=1
                sat_death_mod = 1.5 - 0.8 * sat   # 1.5x at sat=0, 0.7x at sat=1
                # Plebs
                new_plebs = d.pops.plebs * PLEB_BIRTH_RATE * sat_birth_mod
                lost_plebs = d.pops.plebs * PLEB_DEATH_RATE * sat_death_mod
                d.pops.plebs = max(0.0, d.pops.plebs + new_plebs - lost_plebs)
                # Patricians
                new_pat = d.pops.patricians * PATRICIAN_BIRTH_RATE * sat_birth_mod
                lost_pat = d.pops.patricians * PATRICIAN_DEATH_RATE * sat_death_mod
                d.pops.patricians = max(0.0, d.pops.patricians + new_pat - lost_pat)
                # Unrest decays slowly when conditions are good.
                if sat > 0.5:
                    d.pops.unrest = max(0.0, d.pops.unrest - 0.005)
                if d.pops.unrest > 0.6 and rng.random() < d.pops.unrest * 0.3:
                    push_log(
                        state.log,
                        state.tick,
                        LogSeverity.WARNING,
                        f"Unrest stirs in {d.name} ({city.name}).",
                    )

            if weekly:
                # Migration is gated on open house capacity. Empty district →
                # no inflow. Overfilled or unhappy → outflow.
                housing_cap = sum(
                    city.buildings[b_id].residence_capacity()
                    for b_id in d.building_ids
                    if city.buildings[b_id].kind == BuildingKind.RESIDENCE
                    and city.buildings[b_id].is_completed
                )
                open_slots = max(0.0, housing_cap - d.pops.plebs)
                if open_slots > 0 and sat > 0.3:
                    inflow = min(open_slots, MIGRATION_BASE_RATE * sat)
                    d.pops.plebs += inflow
                elif open_slots <= 0 or sat < 0.3:
                    outflow = d.pops.plebs * WEEKLY_OUTFLOW_RATE * (1 + unrest)
                    d.pops.plebs = max(0.0, d.pops.plebs - outflow)
