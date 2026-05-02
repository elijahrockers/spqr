"""Demographics — monthly births, deaths, and migration driven by
satisfaction. Runs only on the monthly boundary; cheap nop on other ticks."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import HOURS_PER_MONTH, GameState


# Monthly base rates (per individual). Tuned for slow but visible growth.
PLEB_BIRTH_RATE = 0.012
PLEB_DEATH_RATE = 0.006
PATRICIAN_BIRTH_RATE = 0.008
PATRICIAN_DEATH_RATE = 0.005


def step(state: GameState, rng: random.Random) -> None:
    if (state.tick % HOURS_PER_MONTH) != 0 or state.tick == 0:
        return
    for city in state.cities:
        for d in city.districts:
            sat = d.satisfaction
            unrest = d.pops.unrest

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

            # Migration: high satisfaction attracts plebs, low pushes them out.
            if sat > 0.7:
                migrated_in = max(1.0, d.pops.plebs * 0.005)
                d.pops.plebs += migrated_in
            elif sat < 0.3:
                migrated_out = d.pops.plebs * 0.005 * (1 + unrest)
                d.pops.plebs = max(0.0, d.pops.plebs - migrated_out)

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
