"""Housing — monthly tier upgrades for residences plus road-proximity
desirability bonus and industrial nuisance penalty.

Tier upgrades: a residence is designated at tier 0 (undeveloped land —
squatter family). Each month, every completed residence with a road
within RESIDENCE_AMENITY_REACH_COST tiles (Dijkstra over the same cost
model the grain pipeline uses) and sufficient timber AND stone in the
treasury advances one tier. Stops at RESIDENCE_MAX_TIER. Tier 1 (huts)
needs only timber; tiers 2 (cottages) and 3 (insula) need both timber
and stone, reflecting heavier masonry.

Tier 2 (cottages) has an additional gate: a completed OFFICE must be
in reach. The office's reach scales with assigned workers
(OFFICE_REACH_PER_WORKER × workers_assigned). This gives civic
densification a real cost — a city without admin infrastructure
can't squeeze plebs into stone cottages.

Industrial nuisance: residences within INDUSTRIAL_NUISANCE_RADIUS
(Chebyshev) of any completed quarry or lumber mill cap at tier 1
(huts) regardless of office or materials, and contribute a monthly
satisfaction penalty to the district. The smoke and noise of
production work makes nearby plots undesirable to upgrade.

Road desirability: independent from tier gating. Each month a district's
satisfaction is bumped by ROAD_DESIRABILITY_BONUS_PER_MONTH × fraction-
of-residences-with-a-road-within-2-tiles (Chebyshev). This is a
proximity check, not a Dijkstra cost cap — a road squeezed against a
house's wall counts the same as one a tile away."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState, is_first_of_month
from spqr.sim.models import (
    INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH,
    INDUSTRIAL_NUISANCE_RADIUS,
    OFFICE_REACH_PER_WORKER,
    RESIDENCE_AMENITY_REACH_COST,
    RESIDENCE_MAX_TIER,
    RESIDENCE_TIER_NAME,
    RESIDENCE_TIER_UPGRADE_STONE_COST,
    RESIDENCE_TIER_UPGRADE_TIMBER_COST,
    ROAD_DESIRABILITY_BONUS_PER_MONTH,
    ROAD_DESIRABILITY_RADIUS,
    BuildingKind,
    City,
    Resources,
)

from .spatial import coverage


# Tier index that needs an office in reach to upgrade (cottages = 2).
COTTAGE_TIER: int = 2

# Maximum tier a residence can reach when in industrial nuisance range.
INDUSTRIAL_NUISANCE_TIER_CEILING: int = 1

# Building kinds that emit industrial nuisance (smoke, noise) — caps
# nearby residences and drags satisfaction.
INDUSTRIAL_NUISANCE_KINDS: frozenset[BuildingKind] = frozenset(
    {BuildingKind.LUMBER_MILL, BuildingKind.QUARRY}
)


def step(state: GameState, rng: random.Random) -> None:
    if not is_first_of_month(state.tick):
        return
    for city in state.cities:
        _upgrade_residences(state, city)
        _apply_road_desirability(city)
        _apply_industrial_nuisance(city)


def _upgrade_residences(state: GameState, city: City) -> None:
    # Compute office coverages and industrial-nuisance tiles once for
    # the month — every gate check reads from these.
    office_coverages = _office_coverages(city)
    nuisance_tiles = _industrial_nuisance_tiles(city)
    # Stable order: ascending building id.
    for b in sorted(city.completed_of(BuildingKind.RESIDENCE), key=lambda b: b.id):
        # Tier ceiling is the smallest of: engine cap, player-set
        # tier_cap, and the industrial-nuisance ceiling if applicable.
        ceiling = min(RESIDENCE_MAX_TIER, b.tier_cap)
        if (b.x, b.y) in nuisance_tiles:
            ceiling = min(ceiling, INDUSTRIAL_NUISANCE_TIER_CEILING)
        if b.tier >= ceiling:
            continue
        next_tier = b.tier + 1
        timber_cost = RESIDENCE_TIER_UPGRADE_TIMBER_COST[next_tier]
        stone_cost = RESIDENCE_TIER_UPGRADE_STONE_COST[next_tier]
        cost = Resources(timber=float(timber_cost), stone=float(stone_cost))
        if not city.treasury.can_pay(cost):
            continue
        if not _has_road_in_reach(city, b.x, b.y):
            continue
        if next_tier == COTTAGE_TIER and not _in_any_office_reach(
            office_coverages, b.x, b.y
        ):
            continue
        city.treasury.pay(cost)
        b.tier = next_tier
        push_log(
            state.log,
            state.tick,
            LogSeverity.GOOD,
            f"Residence at ({b.x},{b.y}) improved to {RESIDENCE_TIER_NAME[b.tier]}.",
        )


def _office_coverages(city: City) -> dict[int, dict[tuple[int, int], float]]:
    """Per-office coverage map. Reach scales with assigned workers —
    an office with 0 workers covers nothing (idle administrative shell);
    an office with 3 workers covers OFFICE_REACH_PER_WORKER × 3 = 18
    cost, roughly a full district when roads are present."""
    out: dict[int, dict[tuple[int, int], float]] = {}
    for b in city.completed_of(BuildingKind.OFFICE):
        if b.workers_assigned <= 0:
            continue
        reach = OFFICE_REACH_PER_WORKER * b.workers_assigned
        out[b.id] = coverage(city, b.x, b.y, reach)
    return out


def _in_any_office_reach(
    coverages: dict[int, dict[tuple[int, int], float]],
    x: int,
    y: int,
) -> bool:
    return any((x, y) in cov for cov in coverages.values())


def _has_road_in_reach(city: City, x: int, y: int) -> bool:
    reach = coverage(city, x, y, RESIDENCE_AMENITY_REACH_COST)
    for (rx, ry) in reach:
        tile = city.tiles[ry * city.width + rx]
        if tile.building_id == -1:
            continue
        b = city.buildings[tile.building_id]
        if b.kind == BuildingKind.ROAD and b.is_completed:
            return True
    return False


def _apply_road_desirability(city: City) -> None:
    """Per district: bump satisfaction by the road-desirability bonus
    scaled by what fraction of completed residences have a road within
    ROAD_DESIRABILITY_RADIUS tiles (Chebyshev). Districts with no
    residences get nothing. The fraction smooths over partial coverage:
    a district where half the houses have a road nearby gets half the
    bonus, not all-or-nothing."""
    for d in city.districts:
        residences = [
            city.buildings[b_id]
            for b_id in d.building_ids
            if city.buildings[b_id].kind == BuildingKind.RESIDENCE
            and city.buildings[b_id].is_completed
        ]
        if not residences:
            continue
        with_road = sum(
            1 for b in residences
            if _road_within_chebyshev(city, b.x, b.y, ROAD_DESIRABILITY_RADIUS)
        )
        fraction = with_road / len(residences)
        if fraction <= 0:
            continue
        d.satisfaction = min(
            1.0, d.satisfaction + ROAD_DESIRABILITY_BONUS_PER_MONTH * fraction
        )


def _road_within_chebyshev(city: City, x: int, y: int, radius: int) -> bool:
    """True if any completed ROAD building lies within Chebyshev distance
    `radius` of (x, y). Cheap rectangular sweep; no Dijkstra needed since
    'within 2 tiles' is a literal tile-distance concept."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if not city.in_bounds(nx, ny):
                continue
            tile = city.tiles[ny * city.width + nx]
            if tile.building_id == -1:
                continue
            b = city.buildings[tile.building_id]
            if b.kind == BuildingKind.ROAD and b.is_completed:
                return True
    return False


def _industrial_nuisance_tiles(city: City) -> set[tuple[int, int]]:
    """Set of (x, y) tiles within INDUSTRIAL_NUISANCE_RADIUS of any
    completed industrial building (lumber mill, quarry). Chebyshev
    distance — same shape as road desirability, but with a wider
    radius reflecting how far smoke and noise carry."""
    tiles: set[tuple[int, int]] = set()
    radius = INDUSTRIAL_NUISANCE_RADIUS
    for kind in INDUSTRIAL_NUISANCE_KINDS:
        for b in city.completed_of(kind):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = b.x + dx, b.y + dy
                    if city.in_bounds(nx, ny):
                        tiles.add((nx, ny))
    return tiles


def _apply_industrial_nuisance(city: City) -> None:
    """Per district: drag satisfaction down by the nuisance penalty
    scaled by what fraction of completed residences sit in the
    nuisance zone. Mirrors `_apply_road_desirability` shape, but
    subtractive."""
    nuisance_tiles = _industrial_nuisance_tiles(city)
    if not nuisance_tiles:
        return
    for d in city.districts:
        residences = [
            city.buildings[b_id]
            for b_id in d.building_ids
            if city.buildings[b_id].kind == BuildingKind.RESIDENCE
            and city.buildings[b_id].is_completed
        ]
        if not residences:
            continue
        affected = sum(
            1 for b in residences if (b.x, b.y) in nuisance_tiles
        )
        if affected == 0:
            continue
        fraction = affected / len(residences)
        d.satisfaction = max(
            0.0,
            d.satisfaction - INDUSTRIAL_NUISANCE_PENALTY_PER_MONTH * fraction,
        )
