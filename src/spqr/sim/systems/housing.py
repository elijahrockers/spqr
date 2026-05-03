"""Housing — monthly tier upgrades for residences.

A residence is designated at tier 0 (undeveloped land — squatter
family). Each month, every completed residence with a road within
RESIDENCE_AMENITY_REACH_COST tiles (Dijkstra over the same cost model
the grain pipeline uses) and sufficient timber AND stone in the
treasury advances one tier. Stops at RESIDENCE_MAX_TIER.

Tier 1 (huts) needs only timber; tiers 2 (cottages) and 3 (insula) need
both timber and stone, reflecting heavier masonry. Roads are the only
amenity in MVP; future tiers will demand water, civic buildings, etc."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import HOURS_PER_MONTH, GameState
from spqr.sim.models import (
    RESIDENCE_AMENITY_REACH_COST,
    RESIDENCE_MAX_TIER,
    RESIDENCE_TIER_NAME,
    RESIDENCE_TIER_UPGRADE_STONE_COST,
    RESIDENCE_TIER_UPGRADE_TIMBER_COST,
    BuildingKind,
    City,
    Resources,
)

from .spatial import coverage


def step(state: GameState, rng: random.Random) -> None:
    if (state.tick % HOURS_PER_MONTH) != 0 or state.tick == 0:
        return
    for city in state.cities:
        _upgrade_residences(state, city)


def _upgrade_residences(state: GameState, city: City) -> None:
    # Stable order: ascending building id.
    for b in sorted(city.buildings, key=lambda b: b.id):
        if b.kind != BuildingKind.RESIDENCE or b.completion < 1.0:
            continue
        if b.tier >= RESIDENCE_MAX_TIER:
            continue
        next_tier = b.tier + 1
        timber_cost = RESIDENCE_TIER_UPGRADE_TIMBER_COST[next_tier]
        stone_cost = RESIDENCE_TIER_UPGRADE_STONE_COST[next_tier]
        cost = Resources(timber=float(timber_cost), stone=float(stone_cost))
        if not city.treasury.can_pay(cost):
            continue
        if not _has_road_in_reach(city, b.x, b.y):
            continue
        city.treasury.pay(cost)
        b.tier = next_tier
        push_log(
            state.log,
            state.tick,
            LogSeverity.GOOD,
            f"Residence at ({b.x},{b.y}) improved to {RESIDENCE_TIER_NAME[b.tier]}.",
        )


def _has_road_in_reach(city: City, x: int, y: int) -> bool:
    reach = coverage(city, x, y, RESIDENCE_AMENITY_REACH_COST)
    for (rx, ry) in reach:
        tile = city.tiles[ry * city.width + rx]
        if tile.building_id == -1:
            continue
        b = city.buildings[tile.building_id]
        if b.kind == BuildingKind.ROAD and b.completion >= 1.0:
            return True
    return False
