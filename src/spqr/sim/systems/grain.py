"""Grain + vegetables system — seasonal growth, harvest, transport, consumption.

Pipeline per tick:
  1. growth   — operational farms in growing months advance grain_maturity
                proportional to assigned workers; on hitting 1.0 the yield
                drops into farm.grain_stored (wheat) or farm.vegetables_stored
                (vegetables) and maturity resets.
  2. transport— wheat farms ship grain to the nearest in-range granary;
                vegetables farms ship vegetables to the nearest in-range
                warehouse. GRAIN_TRANSPORT_RATE per tick per farm.
  3. consume  — pleb meals draw from both granaries (grain) and warehouses
                (vegetables) when both are in reach; meals met from
                multiple food types apply a variety bonus to the
                district's satisfaction. Patrician meals stay grain-only.
  4. sync     — recompute treasury.grain and treasury.vegetables as the
                sum of granary / warehouse inventories.

Spatial reach uses sim.systems.spatial.coverage (Dijkstra with road cost
discount). Coverages are computed once per granary / warehouse per tick
and reused."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState
from spqr.sim.models import (
    CLASS_HOUSING,
    FARM_GRAIN_CAPACITY,
    FARM_TRANSPORT_REACH_COST,
    GRAIN_PER_MEAL,
    GRAIN_TRANSPORT_RATE,
    GRANARY_CAPACITY,
    GRANARY_HISTORY_MAX_SAMPLES,
    GRANARY_REACH_COST,
    GROWING_SEASON_MONTHS,
    MEAL_INTERVAL_HOURS,
    MEAL_OFFSET_HOURS,
    WAREHOUSE_VEGETABLES_CAPACITY,
    BuildingKind,
    City,
    Crop,
    PopClass,
)

from .spatial import coverage


def _is_meal_tick(tick: int, cls: int) -> bool:
    """True iff class `cls` has a scheduled meal on this tick."""
    return (tick - MEAL_OFFSET_HOURS[cls]) % MEAL_INTERVAL_HOURS[cls] == 0


def _pop_count(d, cls: PopClass) -> float:  # type: ignore[no-untyped-def]
    if cls == PopClass.PLEB:
        return d.pops.plebs
    return d.pops.patricians


def step(state: GameState, rng: random.Random) -> None:
    _, month, _ = state.date()
    in_season = month in GROWING_SEASON_MONTHS
    for city in state.cities:
        granary_cov = _granary_coverages(city)
        warehouse_cov = _warehouse_coverages(city)
        _grow_and_harvest(state, city, in_season)
        _transport(state, city, granary_cov, warehouse_cov)
        _consume(state, city, granary_cov, warehouse_cov)
        _sync_treasury_grain(city)
        _sync_treasury_vegetables(city)
        _record_granary_history(city)


def _record_granary_history(city: City) -> None:
    """Append the current grain_stored to each completed granary's
    `inventory_history`, capping at GRANARY_HISTORY_MAX_SAMPLES so save
    files don't grow unbounded."""
    for b in city.completed_of(BuildingKind.GRANARY):
        b.inventory_history.append(b.grain_stored)
        excess = len(b.inventory_history) - GRANARY_HISTORY_MAX_SAMPLES
        if excess > 0:
            del b.inventory_history[:excess]


# --- helpers ----------------------------------------------------------------


def _granary_coverages(city: City) -> dict[int, dict[tuple[int, int], float]]:
    """Per-granary coverage map. Includes only completed granaries."""
    return {
        b.id: coverage(city, b.x, b.y, GRANARY_REACH_COST)
        for b in city.completed_of(BuildingKind.GRANARY)
    }


def _warehouse_coverages(city: City) -> dict[int, dict[tuple[int, int], float]]:
    """Per-warehouse coverage map for vegetables feeding. Same Dijkstra
    cost cap as granaries — vegetables travel as far as grain does."""
    return {
        b.id: coverage(city, b.x, b.y, GRANARY_REACH_COST)
        for b in city.completed_of(BuildingKind.WAREHOUSE)
    }


def _grow_and_harvest(state: GameState, city: City, in_season: bool) -> None:
    if not in_season:
        return
    for b in city.completed_of(BuildingKind.FARM):
        if b.workers_assigned <= 0:
            continue
        # Pick the produce bin based on crop. Both bins share
        # FARM_GRAIN_CAPACITY for now; future iterations may split.
        if b.crop == int(Crop.WHEAT):
            stock = b.grain_stored
        elif b.crop == int(Crop.VEGETABLES):
            stock = b.vegetables_stored
        else:
            continue
        if stock >= FARM_GRAIN_CAPACITY:
            # Storage full; growth pauses until pickup catches up. Keeps a
            # neglected farm from accumulating infinite produce.
            continue
        b.grain_maturity += b.workers_assigned / b.farm_worker_hours_per_harvest()
        if b.grain_maturity >= 1.0:
            b.grain_maturity = 0.0
            yield_amount = b.farm_yield_per_harvest()
            yielded = min(yield_amount, FARM_GRAIN_CAPACITY - stock)
            if b.crop == int(Crop.WHEAT):
                b.grain_stored += yielded
                produce = "grain"
            else:
                b.vegetables_stored += yielded
                produce = "vegetables"
            push_log(
                state.log,
                state.tick,
                LogSeverity.GOOD,
                f"Farm at ({b.x},{b.y}) harvested {yielded:.0f} {produce}.",
            )


def _transport(
    state: GameState,
    city: City,
    granary_cov: dict[int, dict[tuple[int, int], float]],
    warehouse_cov: dict[int, dict[tuple[int, int], float]],
) -> None:
    for farm in city.completed_of(BuildingKind.FARM):
        if farm.crop == int(Crop.WHEAT) and farm.grain_stored > 0:
            target = _nearest_storage_for_farm(
                city, farm, granary_cov,
                kind=BuildingKind.GRANARY,
                stock_attr="grain_stored",
                capacity=GRANARY_CAPACITY,
            )
            if target is None:
                continue
            capacity_left = GRANARY_CAPACITY - target.grain_stored
            amount = min(GRAIN_TRANSPORT_RATE, farm.grain_stored, capacity_left)
            farm.grain_stored -= amount
            target.grain_stored += amount
        elif farm.crop == int(Crop.VEGETABLES) and farm.vegetables_stored > 0:
            target = _nearest_storage_for_farm(
                city, farm, warehouse_cov,
                kind=BuildingKind.WAREHOUSE,
                stock_attr="vegetables_stored",
                capacity=WAREHOUSE_VEGETABLES_CAPACITY,
            )
            if target is None:
                continue
            capacity_left = WAREHOUSE_VEGETABLES_CAPACITY - target.vegetables_stored
            amount = min(
                GRAIN_TRANSPORT_RATE, farm.vegetables_stored, capacity_left
            )
            farm.vegetables_stored -= amount
            target.vegetables_stored += amount


def _nearest_storage_for_farm(
    city: City,
    farm,  # type: ignore[no-untyped-def]
    cov_by_id: dict[int, dict[tuple[int, int], float]],
    *,
    kind: BuildingKind,
    stock_attr: str,
    capacity: float,
):  # type: ignore[no-untyped-def]
    """Find the nearest in-transport-reach storage building of `kind`
    that still has capacity. Used for both grain (granary) and
    vegetables (warehouse) transport."""
    farm_reach = coverage(city, farm.x, farm.y, FARM_TRANSPORT_REACH_COST)
    best = None
    best_cost = float("inf")
    for b in city.completed_of(kind):
        if getattr(b, stock_attr) >= capacity:
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
    warehouse_cov: dict[int, dict[tuple[int, int], float]],
) -> None:
    """Discrete meal events. Each civilian class fires only on its scheduled
    tick (see MEAL_INTERVAL_HOURS / MEAL_OFFSET_HOURS). Outside of meal
    ticks this is a no-op — granary inventories should look like a
    staircase descending across the day, not a smooth slope.

    Pleb meals draw from both granaries (grain) and warehouses
    (vegetables) when both are in reach, splitting demand 50/50. The
    number of distinct food types actually drained from is fed back as a
    variety bonus to district satisfaction."""
    for d in city.districts:
        for cls in (PopClass.PLEB, PopClass.PATRICIAN):
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
                and city.buildings[b_id].is_completed
            ]
            allow_veg = cls == PopClass.PLEB
            unmet, food_types = _serve_meal(
                city, houses, granary_cov, warehouse_cov, demand,
                allow_veg=allow_veg,
            )
            _apply_meal_satisfaction(d, demand, unmet, food_types)


def _serve_meal(
    city: City,
    houses: list,  # type: ignore[type-arg]
    granary_cov: dict[int, dict[tuple[int, int], float]],
    warehouse_cov: dict[int, dict[tuple[int, int], float]],
    demand: float,
    *,
    allow_veg: bool,
) -> tuple[float, int]:
    """Distribute `demand` across `houses` proportional to their housing
    capacity, draining each house's in-range food sources. Returns
    `(unmet, food_types_drawn)` where food_types_drawn is the count of
    distinct food types (1 or 2) that were drained from across the
    district this meal."""
    if not houses:
        unmet = _drain_any_granary(city, demand)
        return unmet, (1 if unmet < demand else 0)
    total_cap = sum(h.residence_capacity() for h in houses)
    if total_cap == 0:
        unmet = _drain_any_granary(city, demand)
        return unmet, (1 if unmet < demand else 0)
    unmet = 0.0
    grain_drawn = False
    veg_drawn = False
    for h in houses:
        share = h.residence_capacity() / total_cap
        house_demand = demand * share
        drained, g_used, v_used = _drain_for_house(
            city, h, granary_cov, warehouse_cov, house_demand,
            allow_veg=allow_veg,
        )
        unmet += house_demand - drained
        grain_drawn = grain_drawn or g_used
        veg_drawn = veg_drawn or v_used
    food_types = int(grain_drawn) + int(veg_drawn)
    return unmet, food_types


def _apply_meal_satisfaction(
    d, demand: float, unmet: float, food_types: int,  # type: ignore[no-untyped-def]
) -> None:
    if unmet > 0:
        ratio = min(1.0, unmet / demand) if demand > 0 else 1.0
        d.satisfaction = max(0.0, d.satisfaction - 0.04 * ratio)
        d.pops.unrest = min(1.0, d.pops.unrest + 0.02 * ratio)
    else:
        # Variety bonus: +0.003 per distinct food type drained on this
        # meal. One source = original behavior; two = double growth.
        bonus = 0.003 * max(1, food_types)
        d.satisfaction = min(1.0, d.satisfaction + bonus)


def _drain_for_house(
    city: City,
    house,  # type: ignore[no-untyped-def]
    granary_cov: dict[int, dict[tuple[int, int], float]],
    warehouse_cov: dict[int, dict[tuple[int, int], float]],
    demand: float,
    *,
    allow_veg: bool,
) -> tuple[float, bool, bool]:
    """Pull `demand` worth of food from in-reach sources for one house.

    When both grain (granary) and vegetables (warehouse) are accessible
    and have stock, demand splits 50/50. If only one source has stock,
    that source carries the full demand. Returns
    `(amount_drained, grain_used, veg_used)`."""
    if demand <= 0:
        return 0.0, False, False
    grain_available = _has_stock_in_reach(
        city, house, granary_cov, "grain_stored",
    )
    veg_available = (
        allow_veg
        and _has_stock_in_reach(
            city, house, warehouse_cov, "vegetables_stored",
        )
    )
    if grain_available and veg_available:
        grain_target = demand * 0.5
        veg_target = demand * 0.5
    elif grain_available:
        grain_target, veg_target = demand, 0.0
    elif veg_available:
        grain_target, veg_target = 0.0, demand
    else:
        return 0.0, False, False
    grain_drained = _drain_from(
        city, house, granary_cov, "grain_stored", grain_target,
    )
    veg_drained = _drain_from(
        city, house, warehouse_cov, "vegetables_stored", veg_target,
    )
    # If one source under-delivered (ran out mid-meal), top up from
    # whatever's left in the other.
    shortfall = (grain_target - grain_drained) + (veg_target - veg_drained)
    if shortfall > 0:
        if veg_target == 0 or grain_drained < grain_target:
            extra_v = _drain_from(
                city, house, warehouse_cov, "vegetables_stored", shortfall,
            ) if allow_veg else 0.0
            veg_drained += extra_v
            shortfall -= extra_v
        if shortfall > 0 and (grain_target == 0 or veg_drained < veg_target):
            extra_g = _drain_from(
                city, house, granary_cov, "grain_stored", shortfall,
            )
            grain_drained += extra_g
    total = grain_drained + veg_drained
    return total, grain_drained > 0, veg_drained > 0


def _has_stock_in_reach(
    city: City,
    house,  # type: ignore[no-untyped-def]
    cov_by_id: dict[int, dict[tuple[int, int], float]],
    stock_attr: str,
) -> bool:
    for b_id, cov in cov_by_id.items():
        if (house.x, house.y) not in cov:
            continue
        if getattr(city.buildings[b_id], stock_attr) > 0:
            return True
    return False


def _drain_from(
    city: City,
    house,  # type: ignore[no-untyped-def]
    cov_by_id: dict[int, dict[tuple[int, int], float]],
    stock_attr: str,
    demand: float,
) -> float:
    """Pull `demand` from the in-reach storage buildings of one type
    (granaries→grain, warehouses→vegetables). Returns amount actually
    drained."""
    if demand <= 0:
        return 0.0
    drained = 0.0
    for b_id in sorted(cov_by_id.keys()):
        if (house.x, house.y) not in cov_by_id[b_id]:
            continue
        b = city.buildings[b_id]
        stock = getattr(b, stock_attr)
        take = min(demand - drained, stock)
        if take <= 0:
            continue
        setattr(b, stock_attr, stock - take)
        drained += take
        if drained >= demand:
            break
    return drained


def _drain_any_granary(city: City, demand: float) -> float:
    """Fallback: pull from any granary, largest first. Returns unmet."""
    granaries = sorted(
        city.completed_of(BuildingKind.GRANARY),
        key=lambda g: (-g.grain_stored, g.id),
    )
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
    city.treasury.grain = sum(
        b.grain_stored for b in city.completed_of(BuildingKind.GRANARY)
    )


def _sync_treasury_vegetables(city: City) -> None:
    """Recompute treasury.vegetables as the sum of warehouse veg
    inventories. Warehouses are authoritative; treasury is a cache."""
    city.treasury.vegetables = sum(
        b.vegetables_stored for b in city.completed_of(BuildingKind.WAREHOUSE)
    )


def drain_treasury_grain(city: City, amount: float) -> float:
    """Drain `amount` from the city's grain stockpile (across granaries
    largest-first). Returns the amount actually drained. Used by the
    economy system for the monthly grain dole."""
    drained = 0.0
    granaries = sorted(
        city.completed_of(BuildingKind.GRANARY),
        key=lambda g: (-g.grain_stored, g.id),
    )
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
