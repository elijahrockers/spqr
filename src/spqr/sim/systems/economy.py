"""Economy: monthly taxation and grain dole.

Hourly grain flow lives in `grain.py` (seasonal growth, transport, per-
house consumption). Economy stays focused on the periodic, city-wide
denominator-of-money side: pulling tax revenue every month and paying the
recurring obligations (dole) by drawing from the granary network.

Taxation is office-gated: only plebs and patricians whose residence
sits in the reach of at least one completed OFFICE pay tax. A city
with no offices collects zero tax. Office reach scales with assigned
workers (OFFICE_REACH_PER_WORKER × workers_assigned), so growing the
admin staff expands the tax base. The grain dole is unaffected — it's
a satisfaction expense, not a range gate, and applies to all plebs."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState, is_first_of_month
from spqr.sim.models import (
    OFFICE_REACH_PER_WORKER,
    BuildingKind,
)

from .grain import drain_treasury_grain
from .spatial import coverage


# Monthly tax in denarii per pleb at tax_rate=1.0. Patricians pay 8x —
# they have a wider tax base.
TAX_PER_PLEB_AT_FULL_RATE = 5.0


def step(state: GameState, rng: random.Random) -> None:
    if not is_first_of_month(state.tick):
        return
    for city in state.cities:
        _apply_monthly(state, city)


def _apply_monthly(state: GameState, city) -> None:  # type: ignore[no-untyped-def]
    # Taxation. Plebs/patricians outside the union of all office
    # coverages don't pay — civic admin is the tax-collection
    # mechanism in this model.
    plebs_total = sum(d.pops.plebs for d in city.districts)
    taxable_plebs, taxable_patricians = _office_taxable_pops(city)

    # added plebs_total into the revenue equation so even without an office, some money is collected.
    # Otherwise, early cities can softlock, player can't create any improving buildings.
    revenue = (
	plebs_total
        + taxable_plebs * TAX_PER_PLEB_AT_FULL_RATE * city.tax_rate
        + taxable_patricians * TAX_PER_PLEB_AT_FULL_RATE * city.tax_rate * 8
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


def _office_taxable_pops(city) -> tuple[float, float]:  # type: ignore[no-untyped-def]
    """Sum plebs and patricians whose residence is in the reach of at
    least one completed office. Per-residence pop is the district's
    pop pro-rated by capacity share — same math the inspector uses
    so the tax base never disagrees with what the player sees.

    Returns (plebs_in_reach, patricians_in_reach). Both are floats."""
    # Union of all office coverage tiles. An office with 0 workers
    # covers nothing — civic shell has no admin.
    covered_tiles: set[tuple[int, int]] = set()
    for off in city.completed_of(BuildingKind.OFFICE):
        if off.workers_assigned <= 0:
            continue
        reach = OFFICE_REACH_PER_WORKER * off.workers_assigned
        covered_tiles.update(coverage(city, off.x, off.y, reach).keys())
    if not covered_tiles:
        return 0.0, 0.0

    plebs = 0.0
    patricians = 0.0
    for d in city.districts:
        # Per-district capacity sums — used to pro-rate pops.
        residence_cap_total = 0
        domus_cap_total = 0
        for b_id in d.building_ids:
            b = city.buildings[b_id]
            if not b.is_completed:
                continue
            if b.kind == BuildingKind.RESIDENCE:
                residence_cap_total += b.residence_capacity()
            elif b.kind == BuildingKind.DOMUS:
                domus_cap_total += b.residence_capacity()
        # Sum the share of each in-reach building.
        for b_id in d.building_ids:
            b = city.buildings[b_id]
            if not b.is_completed:
                continue
            if (b.x, b.y) not in covered_tiles:
                continue
            if b.kind == BuildingKind.RESIDENCE and residence_cap_total > 0:
                share = b.residence_capacity() / residence_cap_total
                plebs += d.pops.plebs * share
            elif b.kind == BuildingKind.DOMUS and domus_cap_total > 0:
                share = b.residence_capacity() / domus_cap_total
                patricians += d.pops.patricians * share
    return plebs, patricians
