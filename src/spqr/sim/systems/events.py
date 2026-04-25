"""Random/scripted events. MVP includes one event class: barbarian raid.

A barbarian camp on the region map rolls each month against its aggression;
on success it launches a raid resolved by raider strength vs garrison."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import HOURS_PER_MONTH, GameState
from spqr.sim.models import SiteKind


def step(state: GameState, rng: random.Random) -> None:
    monthly = (state.tick % HOURS_PER_MONTH) == 0 and state.tick > 0
    if not monthly:
        return
    city = state.player_city()
    for site in state.province.sites:
        if site.kind != SiteKind.BARBARIAN_CAMP:
            continue
        if rng.random() >= site.aggression:
            continue
        _resolve_raid(state, city, site, rng)


def _resolve_raid(state: GameState, city, site, rng: random.Random) -> None:  # type: ignore[no-untyped-def]
    raider = site.strength * rng.uniform(0.7, 1.2)
    defender = city.garrison.legionaries * (1.0 + city.garrison.training) * rng.uniform(0.8, 1.2)
    if defender >= raider:
        # Repulsed. Garrison takes light losses; barbarians lose strength.
        casualties = max(1, int(city.garrison.legionaries * rng.uniform(0.0, 0.1)))
        city.garrison.legionaries = max(0, city.garrison.legionaries - casualties)
        site.strength = max(0, int(site.strength * rng.uniform(0.4, 0.7)))
        push_log(
            state.log,
            state.tick,
            LogSeverity.GOOD,
            f"Raid by {site.name} repulsed; {casualties} legionaries fallen.",
        )
    else:
        # Raid succeeds: looted grain and denarii, civilian casualties.
        looted_grain = min(city.treasury.grain, rng.uniform(20.0, 80.0))
        looted_d = min(city.treasury.denarii, rng.uniform(40.0, 120.0))
        city.treasury.grain -= looted_grain
        city.treasury.denarii -= looted_d
        casualties = max(2, int(city.garrison.legionaries * rng.uniform(0.2, 0.4)))
        city.garrison.legionaries = max(0, city.garrison.legionaries - casualties)
        for d in city.districts:
            losses = d.pops.plebs * rng.uniform(0.005, 0.02)
            d.pops.plebs = max(0.0, d.pops.plebs - losses)
            d.satisfaction = max(0.0, d.satisfaction - 0.10)
            d.pops.unrest = min(1.0, d.pops.unrest + 0.10)
        push_log(
            state.log,
            state.tick,
            LogSeverity.BAD,
            f"Raid by {site.name} succeeded! "
            f"{looted_grain:.0f} grain and {looted_d:.0f} denarii lost.",
        )
