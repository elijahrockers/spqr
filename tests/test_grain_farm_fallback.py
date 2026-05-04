"""Tests for the third-pass eat-from-farms fallback in `grain.py`.

When a residence's in-reach granaries / warehouses can't fully cover
a meal, the meal drains farms in reach directly. Farms intentionally
stay out of `treasury.grain` / `treasury.vegetables` (those mirror
granary / warehouse inventories only), so a farm-fed meal must not
inflate the cached aggregates the dole and tax base read."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    Crop,
    GRAIN_PER_MEAL,
    MEAL_INTERVAL_HOURS,
    MEAL_OFFSET_HOURS,
)
from spqr.sim.systems import default_systems

from ._helpers import find_clear_grass


def _city_with_residence_and_farm(
    *,
    plebs: float = 4.0,
    farm_in_reach: bool = True,
):
    """Designate a residence and an adjacent (or far) wheat farm.
    Hand-finish the farm so the test starts from an operational
    baseline. No granary, so granary coverage is empty — the meal
    must fall through to the farm."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    res_xy = find_clear_grass(city)
    if farm_in_reach:
        # Adjacent tile if buildable, else next-closest grass.
        near = (res_xy[0] + 1, res_xy[1])
        if not city.is_buildable(*near):
            near = find_clear_grass(city, exclude={res_xy})
        farm_xy = near
    else:
        # Push the farm to the opposite edge of the map. Far enough
        # that FARM_TRANSPORT_REACH_COST (16) won't reach.
        far_x = (res_xy[0] + city.width // 2) % city.width
        far_y = (res_xy[1] + city.height // 2) % city.height
        # Find the nearest buildable tile to (far_x, far_y).
        farm_xy = _nearest_buildable(city, far_x, far_y, exclude={res_xy})
    eng.submit(PlaceZone(x=res_xy[0], y=res_xy[1], kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=farm_xy[0], y=farm_xy[1], kind=ZoneKind.FARM))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    farm.completion = 1.0
    farm.crop = int(Crop.WHEAT)
    city.districts[0].pops.plebs = plebs
    return state, eng, city, res, farm


def _nearest_buildable(city, x: int, y: int, exclude: set) -> tuple[int, int]:
    best = None
    best_d = float("inf")
    for yy in range(city.height):
        for xx in range(city.width):
            if (xx, yy) in exclude:
                continue
            if not city.is_buildable(xx, yy):
                continue
            d = abs(xx - x) + abs(yy - y)
            if d < best_d:
                best_d = d
                best = (xx, yy)
    if best is None:
        raise RuntimeError("no buildable tile available")
    return best


def _step_until_pleb_meal(eng: Engine, max_ticks: int = 48) -> bool:
    """Advance the engine until the next pleb meal tick fires.
    Returns True if a meal hour ran during the loop, False on
    timeout."""
    interval = MEAL_INTERVAL_HOURS[0]
    offset = MEAL_OFFSET_HOURS[0]
    fired = False
    for _ in range(max_ticks):
        eng.step(1)
        if (eng.state.tick - offset) % interval == 0:
            fired = True
            break
    return fired


def test_meal_drains_in_reach_farm_when_no_granary():
    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=True,
    )
    farm.grain_stored = 50.0
    initial_stock = farm.grain_stored
    assert _step_until_pleb_meal(eng), "pleb meal never fired in test window"
    # Farm buffer dropped — the meal pulled from the field directly.
    assert farm.grain_stored < initial_stock
    drop = initial_stock - farm.grain_stored
    expected = 4.0 * GRAIN_PER_MEAL[0]
    # Allow for some growth on the same tick (it's growing season in
    # March), but the drop should be at least the meal demand.
    assert drop >= expected - 1e-6


def test_treasury_grain_unchanged_by_farm_drain():
    """A farm-fed meal must not move `treasury.grain` — that field
    mirrors granary inventories only. Inflating it via farm buffers
    would silently widen the dole's draw and the tax base's
    denominator."""
    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=True,
    )
    farm.grain_stored = 50.0
    assert _step_until_pleb_meal(eng)
    assert city.treasury.grain == 0.0


def test_meal_unmet_when_farm_out_of_reach():
    """With the farm pushed beyond FARM_TRANSPORT_REACH_COST, the
    meal can't fall through to it. Farm buffer stays put; the
    meal logs an unmet shortfall (district satisfaction drops)."""
    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=False,
    )
    farm.grain_stored = 50.0
    initial_stock = farm.grain_stored
    initial_sat = city.districts[0].satisfaction
    assert _step_until_pleb_meal(eng)
    assert farm.grain_stored == initial_stock
    # Satisfaction took a hit on the unmet meal.
    assert city.districts[0].satisfaction < initial_sat


def test_vegetable_farm_in_reach_feeds_pleb():
    """Pleb meals are mixed-diet (allow_veg=True). A vegetables farm
    in reach should drain its `vegetables_stored` buffer when no
    warehouse is around."""
    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=True,
    )
    farm.crop = int(Crop.VEGETABLES)
    farm.grain_stored = 0.0
    farm.vegetables_stored = 50.0
    initial_veg = farm.vegetables_stored
    assert _step_until_pleb_meal(eng)
    assert farm.vegetables_stored < initial_veg


def test_dole_drains_farm_when_no_granary():
    """drain_treasury_grain falls through to wheat farms after
    granaries. With no granary at all, the dole still gets paid out
    of the field — matches the player's mental model now that meals
    eat from farms directly. The treasury cache still mirrors only
    granaries (farms intentionally stay out)."""
    from spqr.sim.systems.grain import drain_treasury_grain

    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=True,
    )
    farm.grain_stored = 100.0
    drained = drain_treasury_grain(city, 30.0)
    assert drained == 30.0
    assert farm.grain_stored == 70.0
    assert city.treasury.grain == 0.0


def test_dole_partial_when_neither_granary_nor_farm_has_enough():
    """If neither granaries nor farms can cover the demand, the dole
    drains what's there and returns the partial amount — same shape
    as the granary-only path, just with farms padding the supply."""
    from spqr.sim.systems.grain import drain_treasury_grain

    state, eng, city, res, farm = _city_with_residence_and_farm(
        plebs=4.0, farm_in_reach=True,
    )
    farm.grain_stored = 5.0
    drained = drain_treasury_grain(city, 30.0)
    assert drained == 5.0
    assert farm.grain_stored == 0.0
