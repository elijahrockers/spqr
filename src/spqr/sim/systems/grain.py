"""Grain system — seasonal growth, harvest, transport, consumption.

Pipeline per tick:
  1. growth   — operational farms in growing months advance grain_maturity
                proportional to assigned workers; on hitting 1.0 a yield
                drops into farm.grain_stored and maturity resets.
  2. transport— each farm with stored grain ships GRAIN_TRANSPORT_RATE per
                tick to the nearest in-range granary that has capacity.
  3. consume  — civilian housing pulls its share of district hourly demand
                from in-range granaries. Unmet demand is starvation.
  4. sync     — recompute treasury.grain as the sum of granary inventories
                so status bar / population screen / save files stay
                meaningful with the simpler aggregate.

Spatial reach uses sim.systems.spatial.coverage (Dijkstra with road cost
discount). Coverages are computed once per granary per tick and reused."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState
from spqr.sim.models import (
    CLASS_HOUSING,
    FARM_GRAIN_CAPACITY,
    FARM_TRANSPORT_REACH_COST,
    FARM_WORKER_HOURS_PER_HARVEST,
    GRAIN_PER_LEGIONARY_MEAL,
    GRAIN_PER_MEAL,
    GRAIN_TRANSPORT_RATE,
    GRAIN_YIELD_PER_HARVEST,
    GRANARY_CAPACITY,
    GRANARY_HISTORY_MAX_SAMPLES,
    GRANARY_REACH_COST,
    GROWING_SEASON_MONTHS,
    HOUSING_CAPACITY,
    LEGIONARY_MEAL_INTERVAL_HOURS,
    LEGIONARY_MEAL_OFFSET_HOURS,
    MEAL_INTERVAL_HOURS,
    MEAL_OFFSET_HOURS,
    BuildingKind,
    City,
    PopClass,
)

from .spatial import coverage


def _is_meal_tick(tick: int, cls: int) -> bool:
    """True iff class `cls` has a scheduled meal on this tick."""
    return (tick - MEAL_OFFSET_HOURS[cls]) % MEAL_INTERVAL_HOURS[cls] == 0


def _is_legionary_meal_tick(tick: int) -> bool:
    return (
        tick - LEGIONARY_MEAL_OFFSET_HOURS
    ) % LEGIONARY_MEAL_INTERVAL_HOURS == 0


def _pop_count(d, cls: PopClass) -> float:  # type: ignore[no-untyped-def]
    if cls == PopClass.SLAVE:
        return d.pops.slaves
    if cls == PopClass.PLEB:
        return d.pops.plebs
    if cls == PopClass.EQUES:
        return d.pops.equites
    return d.pops.patricians


def step(state: GameState, rng: random.Random) -> None:
    _, month, _ = state.date()
    in_season = month in GROWING_SEASON_MONTHS
    for city in state.cities:
        granary_cov = _granary_coverages(city)
        _grow_and_harvest(state, city, in_season)
        _transport(state, city, granary_cov)
        _consume(state, city, granary_cov)
        _sync_treasury_grain(city)
        _record_granary_history(city)


def _record_granary_history(city: City) -> None:
    """Append the current grain_stored to each completed granary's
    `inventory_history`, capping at GRANARY_HISTORY_MAX_SAMPLES so save
    files don't grow unbounded."""
    for b in city.buildings:
        if b.kind != BuildingKind.GRANARY or b.completion < 1.0:
            continue
        b.inventory_history.append(b.grain_stored)
        excess = len(b.inventory_history) - GRANARY_HISTORY_MAX_SAMPLES
        if excess > 0:
            del b.inventory_history[:excess]


# --- helpers ----------------------------------------------------------------


def _granary_coverages(city: City) -> dict[int, dict[tuple[int, int], float]]:
    """Per-granary coverage map. Includes only completed granaries."""
    out: dict[int, dict[tuple[int, int], float]] = {}
    for b in city.buildings:
        if b.kind != BuildingKind.GRANARY or b.completion < 1.0:
            continue
        out[b.id] = coverage(city, b.x, b.y, GRANARY_REACH_COST)
    return out


def _grow_and_harvest(state: GameState, city: City, in_season: bool) -> None:
    if not in_season:
        return
    for b in city.buildings:
        if b.kind != BuildingKind.FARM or b.completion < 1.0:
            continue
        if b.workers_assigned <= 0:
            continue
        if b.grain_stored >= FARM_GRAIN_CAPACITY:
            # Storage full; growth pauses until pickup catches up. Keeps a
            # neglected farm from accumulating infinite grain.
            continue
        b.grain_maturity += b.workers_assigned / FARM_WORKER_HOURS_PER_HARVEST
        if b.grain_maturity >= 1.0:
            b.grain_maturity = 0.0
            yielded = min(GRAIN_YIELD_PER_HARVEST, FARM_GRAIN_CAPACITY - b.grain_stored)
            b.grain_stored += yielded
            push_log(
                state.log,
                state.tick,
                LogSeverity.GOOD,
                f"Farm at ({b.x},{b.y}) harvested {yielded:.0f} grain.",
            )


def _transport(
    state: GameState,
    city: City,
    granary_cov: dict[int, dict[tuple[int, int], float]],
) -> None:
    for farm in city.buildings:
        if farm.kind != BuildingKind.FARM or farm.completion < 1.0:
            continue
        if farm.grain_stored <= 0:
            continue
        target = _nearest_granary_for_farm(city, farm, granary_cov)
        if target is None:
            continue
        capacity_left = GRANARY_CAPACITY - target.grain_stored
        if capacity_left <= 0:
            continue
        amount = min(GRAIN_TRANSPORT_RATE, farm.grain_stored, capacity_left)
        farm.grain_stored -= amount
        target.grain_stored += amount


def _nearest_granary_for_farm(
    city: City,
    farm,  # type: ignore[no-untyped-def]
    granary_cov: dict[int, dict[tuple[int, int], float]],
):  # type: ignore[no-untyped-def]
    # Use a wider transport reach than feeding reach: farms can ship grain
    # further than a granary can serve houses. Compute a separate coverage
    # from the FARM's tile so we use the same Dijkstra metric in reverse.
    farm_reach = coverage(city, farm.x, farm.y, FARM_TRANSPORT_REACH_COST)
    best = None
    best_cost = float("inf")
    for b in city.buildings:
        if b.kind != BuildingKind.GRANARY or b.completion < 1.0:
            continue
        if b.grain_stored >= GRANARY_CAPACITY:
            continue
        c = farm_reach.get((b.x, b.y))
        if c is None:
            continue
        if c < best_cost:
            best = b
            best_cost = c
    return best


def _consume(
    state: GameState,
    city: City,
    granary_cov: dict[int, dict[tuple[int, int], float]],
) -> None:
    """Discrete meal events. Each civilian class fires only on its scheduled
    tick (see MEAL_INTERVAL_HOURS / MEAL_OFFSET_HOURS). Legionaries eat
    twice daily from granaries serving the barracks. Outside of meal ticks
    this is a no-op — granary inventories should look like a staircase
    descending across the day, not a smooth slope."""
    for d in city.districts:
        for cls in (PopClass.SLAVE, PopClass.PLEB, PopClass.EQUES, PopClass.PATRICIAN):
            cls_id = int(cls)
            if not _is_meal_tick(state.tick, cls_id):
                continue
            count = _pop_count(d, cls)
            if count <= 0:
                continue
            demand = count * GRAIN_PER_MEAL[cls_id]
            housing_kind = CLASS_HOUSING[cls_id]
            houses = [
                city.buildings[b_id]
                for b_id in d.building_ids
                if city.buildings[b_id].kind == housing_kind
                and city.buildings[b_id].completion >= 1.0
            ]
            unmet = _serve_meal(city, houses, granary_cov, demand)
            _apply_meal_satisfaction(d, demand, unmet)

    # Soldiers — per-city not per-district. Eat from granaries serving any
    # completed barracks tile.
    if _is_legionary_meal_tick(state.tick) and city.garrison.legionaries > 0:
        demand = city.garrison.legionaries * GRAIN_PER_LEGIONARY_MEAL
        barracks = [
            b for b in city.buildings
            if b.kind == BuildingKind.BARRACKS and b.completion >= 1.0
        ]
        _serve_meal(city, barracks, granary_cov, demand)


def _serve_meal(
    city: City,
    houses: list,  # type: ignore[type-arg]
    granary_cov: dict[int, dict[tuple[int, int], float]],
    demand: float,
) -> float:
    """Distribute `demand` across `houses` proportional to their housing
    capacity, draining each house's in-range granaries. If there are no
    houses of the right kind, fall back to any granary in the city.
    Returns the unmet portion of the demand."""
    if not houses:
        return _drain_any_granary(city, demand)
    total_cap = sum(HOUSING_CAPACITY.get(h.kind, 0) for h in houses)
    if total_cap == 0:
        # Buildings exist but have no housing capacity (e.g. no barracks
        # yet on a class that doesn't normally need housing). Fall back.
        return _drain_any_granary(city, demand)
    unmet = 0.0
    for h in houses:
        share = HOUSING_CAPACITY.get(h.kind, 0) / total_cap
        house_demand = demand * share
        drained = _drain_for_house(city, h, granary_cov, house_demand)
        unmet += house_demand - drained
    return unmet


def _apply_meal_satisfaction(d, demand: float, unmet: float) -> None:  # type: ignore[no-untyped-def]
    if unmet > 0:
        ratio = min(1.0, unmet / demand) if demand > 0 else 1.0
        d.satisfaction = max(0.0, d.satisfaction - 0.04 * ratio)
        d.pops.unrest = min(1.0, d.pops.unrest + 0.02 * ratio)
    else:
        d.satisfaction = min(1.0, d.satisfaction + 0.003)


def _drain_for_house(
    city: City,
    house,  # type: ignore[no-untyped-def]
    granary_cov: dict[int, dict[tuple[int, int], float]],
    demand: float,
) -> float:
    """Pull `demand` grain from granaries whose coverage includes the house's
    tile. Returns the amount actually drained."""
    if demand <= 0:
        return 0.0
    drained = 0.0
    # Stable iteration: by granary id ascending.
    for g_id in sorted(granary_cov.keys()):
        if (house.x, house.y) not in granary_cov[g_id]:
            continue
        granary = city.buildings[g_id]
        take = min(demand - drained, granary.grain_stored)
        if take <= 0:
            continue
        granary.grain_stored -= take
        drained += take
        if drained >= demand:
            break
    return drained


def _drain_any_granary(city: City, demand: float) -> float:
    """Fallback: pull from any granary, largest first. Returns unmet."""
    granaries = [
        b for b in city.buildings
        if b.kind == BuildingKind.GRANARY and b.completion >= 1.0
    ]
    granaries.sort(key=lambda g: (-g.grain_stored, g.id))
    remaining = demand
    for g in granaries:
        take = min(remaining, g.grain_stored)
        if take <= 0:
            continue
        g.grain_stored -= take
        remaining -= take
        if remaining <= 0:
            break
    return max(0.0, remaining)


def _sync_treasury_grain(city: City) -> None:
    """Recompute treasury.grain as the sum of granary inventories. The
    treasury value is now a cached aggregate; granaries are authoritative."""
    total = 0.0
    for b in city.buildings:
        if b.kind == BuildingKind.GRANARY and b.completion >= 1.0:
            total += b.grain_stored
    city.treasury.grain = total


def drain_treasury_grain(city: City, amount: float) -> float:
    """Drain `amount` from the city's grain stockpile (across granaries
    largest-first). Returns the amount actually drained. Used by the
    economy system for monthly garrison upkeep + dole."""
    drained = 0.0
    granaries = [
        b for b in city.buildings
        if b.kind == BuildingKind.GRANARY and b.completion >= 1.0
    ]
    granaries.sort(key=lambda g: (-g.grain_stored, g.id))
    remaining = amount
    for g in granaries:
        take = min(remaining, g.grain_stored)
        if take <= 0:
            continue
        g.grain_stored -= take
        drained += take
        remaining -= take
        if remaining <= 0:
            break
    _sync_treasury_grain(city)
    return drained
