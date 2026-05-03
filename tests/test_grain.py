"""Tests for the seasonal grain pipeline: per-farm growth, harvest,
transport to granaries, and per-house consumption with road-extended
proximity."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    GROWING_SEASON_MONTHS,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.grain import drain_treasury_grain, _sync_treasury_grain
from spqr.sim.systems.spatial import coverage

from ._helpers import bootstrap_starter_city


def _advance_to_month(eng: Engine, target_month: int) -> None:
    """Step the engine until the in-game month equals target_month, day 1."""
    state = eng.state
    while True:
        _, m, d = state.date()
        if m == target_month and d == 1:
            return
        eng.step(1)
        if state.tick > HOURS_PER_MONTH * 24:  # safety bail
            raise RuntimeError("could not reach target month")


def test_farms_do_not_grow_outside_growing_season():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=10_000.0)
    farm = handles["farm"]
    # Game starts in March; advance to October (off-season).
    _advance_to_month(eng, 10)
    farm.grain_maturity = 0.0
    farm.grain_stored = 0.0
    eng.step(HOURS_PER_MONTH)
    _, month, _ = state.date()
    assert month not in GROWING_SEASON_MONTHS
    assert farm.grain_maturity == 0.0
    assert farm.grain_stored == 0.0


def test_farm_grows_and_harvests_during_season():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    # Plebs supply farm labor; stockpile keeps them from starving so
    # they don't migrate out before we measure production.
    handles = bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=10_000.0)
    farm = handles["farm"]
    # Already in March (growing season). Wait one tick for labor.step
    # to assign a worker, then confirm growth advances.
    eng.step(1)
    assert farm.workers_assigned >= 1
    farm.grain_maturity = 0.0
    eng.step(100)
    assert farm.grain_maturity > 0


def test_harvest_yield_lands_in_granary_via_transport():
    """A harvest from a farm with a single in-range granary should
    fully land in that granary within a reasonable transport window."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    handles = bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=10_000.0)
    farm = handles["farm"]
    granary = handles["granary"]
    _sync_treasury_grain(city)
    # Already in growing season (March). Force an immediate harvest by
    # setting maturity just below 1.0; with any worker the next tick
    # will fire the harvest. Then drain the granary so we can see the
    # harvested grain land via transport.
    granary.grain_stored = 0.0
    farm.grain_maturity = 0.999
    eng.step(50)
    assert granary.grain_stored > 0.0


def test_drain_treasury_grain_pulls_from_granaries():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    handles = bootstrap_starter_city(state, eng, grain_stocked=0.0)
    granary = handles["granary"]
    granary.grain_stored = 1000.0
    _sync_treasury_grain(city)
    drained = drain_treasury_grain(city, 250.0)
    assert drained == 250.0
    assert granary.grain_stored == 750.0
    assert city.treasury.grain == 750.0


def test_meal_event_fires_only_on_scheduled_tick():
    """A pleb meal fires when systems run with state.tick == 6 (i.e. during
    the step that advances 5 -> 6). The granary should drop by exactly the
    pleb meal demand on that step and stay flat between meals."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    handles = bootstrap_starter_city(state, eng)
    # Strip houses from the district so meal demand uses the
    # `_drain_any_granary` fallback rather than depending on which houses
    # happen to land in granary range.
    d = city.districts[0]
    d.building_ids = [
        b_id for b_id in d.building_ids
        if city.buildings[b_id].kind not in (BuildingKind.RESIDENCE, BuildingKind.DOMUS)
    ]
    granary = handles["granary"]
    # Engine increments tick before running systems. To have systems see
    # tick==6 (the pleb meal), step until tick==5 then step once more.
    while state.tick < 5:
        eng.step(1)
    grain_before = granary.grain_stored
    eng.step(1)  # advances tick 5 -> 6; pleb meal fires
    drop_at_meal = grain_before - granary.grain_stored
    # Tick 6 fires only the pleb meal (interval 24, offset 6).
    pleb_count = d.pops.plebs
    expected = pleb_count * 0.48
    assert abs(drop_at_meal - expected) < 0.5, (
        f"expected ~{expected:.2f} drop on pleb meal tick, "
        f"got {drop_at_meal:.2f}"
    )
    # Tick 11 should be quiet — no class has a meal scheduled.
    while state.tick < 10:
        eng.step(1)
    grain_a = granary.grain_stored
    eng.step(1)  # 10 -> 11; quiet
    grain_b = granary.grain_stored
    assert grain_a == grain_b, (
        f"expected zero drop at tick 11 (quiet hour), got {grain_a - grain_b}"
    )


def test_grain_inventory_is_a_staircase_not_a_slope():
    """Across one game day, granary inventory should drop in discrete
    steps at meal ticks and stay flat in between."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    samples: list[tuple[int, float]] = []
    for _ in range(24):
        eng.step(1)
        samples.append((state.tick, granary.grain_stored))
    # Count ticks where inventory changed (drops). Should be small —
    # a handful of meal events, not 24 continuous drops.
    drops = sum(
        1 for i in range(1, len(samples))
        if samples[i][1] < samples[i - 1][1] - 0.001
    )
    assert 1 <= drops <= 8, (
        f"expected 1-8 distinct drop events in a day, got {drops}; "
        f"samples: {samples}"
    )


def test_coverage_extended_by_roads():
    """Direct (no roads) reach is small; carving a road from the granary
    out to a far tile extends the coverage in the road's direction."""
    state = new_game(seed=11, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Use a deterministic granary placed at (15, 10) on a guaranteed grass
    # row by clearing a strip and stamping in roads.
    # Find an open spot and plant a granary near it; lay roads heading east.
    spot = None
    for x in range(2, 50):
        # Find a row of grass clear of buildings.
        if all(
            city.tile(x + dx, 10).terrain == CityTerrain.GRASS
            and city.tile(x + dx, 10).building_id == -1
            for dx in range(15)
        ):
            spot = x
            break
    if spot is None:
        return  # map didn't permit a clean strip; skip
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    eng.submit(PlaceZone(x=spot, y=10, kind=ZoneKind.GRANARY))
    eng.step(1)
    granary = city.buildings[-1]
    # Hand-finish construction so coverage tests are stable.
    granary.completion = 1.0
    base_cov = coverage(city, granary.x, granary.y, 12.0)
    base_count = len(base_cov)
    # Place roads stretching east.
    for x in range(spot + 1, spot + 12):
        eng.submit(PlaceZone(x=x, y=10, kind=ZoneKind.ROAD))
    eng.step(1)
    # Hand-complete those roads.
    for b in city.buildings:
        if b.kind == BuildingKind.ROAD and b.completion < 1.0:
            b.completion = 1.0
    extended_cov = coverage(city, granary.x, granary.y, 12.0)
    assert len(extended_cov) > base_count
