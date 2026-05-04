"""Tests for the priority-bucketed labor allocation in
`sim/systems/labor.step`. Default priority puts CONSTRUCTION first
and FARMS second; flipping the order should rearrange
`workers_assigned` predictably while preserving placement order
within a bucket."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BUILDER_SLOTS,
    BuildingKind,
    CityTerrain,
    LaborCategory,
)
from spqr.sim.systems import default_systems

from ._helpers import (
    find_clear_grass,
    find_clear_grass_adjacent_to,
)


def _adjacency_for(kind: ZoneKind) -> set[CityTerrain] | None:
    if kind == ZoneKind.LUMBER_MILL:
        return {CityTerrain.FOREST}
    if kind == ZoneKind.QUARRY:
        return {CityTerrain.HILL, CityTerrain.ROCK}
    return None


def _designate_building(eng: Engine, city, kind: ZoneKind, used: set):
    needed = _adjacency_for(kind)
    if needed is None:
        spot = find_clear_grass(city, used)
    else:
        spot = find_clear_grass_adjacent_to(city, needed, exclude=used)
    used.add(spot)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=kind))
    return spot


def _build_priority_city(plebs: float = 6.0):
    """Set up a city with a completed farm, a completed lumber mill,
    and an under-construction quarry. Workforce sized so only two of
    the three buckets fill at full slot count under the default
    priority. Lumber mill operational slots = 2; farm wheat slots = 3
    (CROP_WORKER_SLOTS); quarry construction = 2 builders.

    `plebs` defaults to 6 — two filled buckets each at ~3 workers."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0

    used: set[tuple[int, int]] = set()
    _designate_building(eng, city, ZoneKind.FARM, used)
    _designate_building(eng, city, ZoneKind.LUMBER_MILL, used)
    _designate_building(eng, city, ZoneKind.QUARRY, used)
    eng.step(1)

    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    mill = next(b for b in city.buildings if b.kind == BuildingKind.LUMBER_MILL)
    quarry = next(b for b in city.buildings if b.kind == BuildingKind.QUARRY)
    farm.completion = 1.0
    mill.completion = 1.0
    # Quarry stays under construction (default completion < 1.0 from designate).
    assert quarry.is_under_construction

    city.districts[0].pops.plebs = plebs
    return state, eng, city, farm, mill, quarry


def test_default_priority_fills_construction_then_farms():
    """Default order is [CONSTRUCTION, FARMS, LUMBER_MILLS, ...]. With
    6 workers the under-construction quarry takes 2 builders, the
    wheat farm takes 3, and the lumber mill gets the leftover 1."""
    state, eng, city, farm, mill, quarry = _build_priority_city(plebs=6.0)
    eng.step(1)
    assert quarry.workers_assigned == BUILDER_SLOTS[BuildingKind.QUARRY]  # 2
    assert farm.workers_assigned == 3
    assert mill.workers_assigned == 1


def test_lumber_mills_first_priority_starves_construction():
    """Move LUMBER_MILLS to the top of the priority list. With 6
    workers the mill fills its 2 operational slots first; the
    quarry-under-construction still gets builders next via
    CONSTRUCTION (next in the new order); the farm picks up what's
    left after that."""
    state, eng, city, farm, mill, quarry = _build_priority_city(plebs=6.0)
    city.labor_priority = [
        int(LaborCategory.LUMBER_MILLS),
        int(LaborCategory.CONSTRUCTION),
        int(LaborCategory.FARMS),
        int(LaborCategory.QUARRIES),
        int(LaborCategory.WORKSHOPS),
        int(LaborCategory.OFFICES),
    ]
    eng.step(1)
    assert mill.workers_assigned == 2
    assert quarry.workers_assigned == 2  # construction gets next slice
    assert farm.workers_assigned == 2    # leftover


def test_workforce_smaller_than_top_bucket_starves_others():
    """With only 1 worker and CONSTRUCTION first, all the labor goes
    to the under-construction quarry; both completed buildings sit
    idle. Confirms strict bucket order, not interleaving."""
    state, eng, city, farm, mill, quarry = _build_priority_city(plebs=1.0)
    eng.step(1)
    assert quarry.workers_assigned == 1  # only 1 builder available
    assert farm.workers_assigned == 0
    assert mill.workers_assigned == 0


def test_allocation_deterministic_across_runs():
    """Same priority + same buildings + same workforce ⇒ same
    workers_assigned vector. Pin determinism so a future refactor
    that introduces, say, dict iteration order doesn't silently
    diverge between runs."""
    state_a, eng_a, _, _, _, _ = _build_priority_city(plebs=6.0)
    eng_a.step(1)
    snapshot_a = sorted(
        (b.id, b.workers_assigned) for b in state_a.player_city().buildings
    )

    state_b, eng_b, _, _, _, _ = _build_priority_city(plebs=6.0)
    eng_b.step(1)
    snapshot_b = sorted(
        (b.id, b.workers_assigned) for b in state_b.player_city().buildings
    )

    assert snapshot_a == snapshot_b


def test_buildings_with_no_bucket_get_zero_workers():
    """Granaries / residences / roads aren't in any LaborCategory
    bucket; they should always end up with `workers_assigned == 0`
    regardless of the priority list."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    used: set[tuple[int, int]] = set()
    _designate_building(eng, city, ZoneKind.GRANARY, used)
    _designate_building(eng, city, ZoneKind.RESIDENCE, used)
    eng.step(1)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.completion = 1.0
    city.districts[0].pops.plebs = 50.0
    eng.step(1)
    # Granary takes WORKER_SLOTS[GRANARY] = 2 — but granary isn't in
    # any LaborCategory bucket, so labor.step zeros it.
    assert granary.workers_assigned == 0
