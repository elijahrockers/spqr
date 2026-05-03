"""Economy: monthly taxation and grain dole.

Hourly grain flow lives in `grain.py` (seasonal growth, transport, per-
house consumption). Economy stays focused on the periodic, city-wide
denominator-of-money side: pulling tax revenue every month and paying the
recurring obligations (dole) by drawing from the granary network."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState, is_first_of_month

from .grain import drain_treasury_grain


# Monthly tax in denarii per pleb at tax_rate=1.0. Patricians pay 8x —
# they have a wider tax base.
TAX_PER_PLEB_AT_FULL_RATE = 5.0


def step(state: GameState, rng: random.Random) -> None:
    if not is_first_of_month(state.tick):
        return
    for city in state.cities:
        _apply_monthly(state, city)


def _apply_monthly(state: GameState, city) -> None:  # type: ignore[no-untyped-def]
    # Taxation
    plebs_total = sum(d.pops.plebs for d in city.districts)
    pat_total = sum(d.pops.patricians for d in city.districts)
    revenue = (
        plebs_total * TAX_PER_PLEB_AT_FULL_RATE * city.tax_rate
        + pat_total * TAX_PER_PLEB_AT_FULL_RATE * city.tax_rate * 8
    )
    city.treasury.denarii += revenue

    # Grain dole — lifts pleb satisfaction, drains the granary network.
    if city.grain_dole_per_pleb > 0:
        needed = plebs_total * city.grain_dole_per_pleb
        drained = drain_treasury_grain(city, needed)
        if drained >= needed - 1e-6:
            for d in city.districts:
                d.satisfaction = min(1.0, d.satisfaction + 0.05)
        else:
            push_log(
                state.log,
                state.tick,
                LogSeverity.WARNING,
                f"{city.name}: grain dole could not be paid in full "
                f"({drained:.0f} of {needed:.0f}).",
            )
