"""Tests for the vegetables food pipeline and food-variety bonus.

Mirrors the grain pipeline tests: vegetables farms harvest into
`vegetables_stored`, ship to warehouses, plebs draw from both food
types when both are in reach, and the variety bonus doubles the
per-meal satisfaction tick."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, SetFarmCrop, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    Crop,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.grain import _sync_treasury_vegetables

from ._helpers import bootstrap_starter_city, find_clear_grass


def _advance_to_month(eng, target_month):
    state = eng.state
    while True:
        _, m, _ = state.date()
        if m == target_month:
            return
        eng.step(1)
        if state.tick > HOURS_PER_MONTH * 24:
            raise RuntimeError("safety bail")


def test_vegetables_farm_harvests_into_farm_vegetables_stored():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=0.0, grain_stocked=0.0)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    eng.submit(SetFarmCrop(building_id=farm.id, crop=int(Crop.VEGETABLES)))
    _advance_to_month(eng, 5)  # mid growing season
    initial = farm.vegetables_stored
    # Vegetables: 4 workers × 120 hours = 480 worker-hours/harvest. Run
    # well past one full cycle. With only 1 farm there's no warehouse
    # destination, so produce should pile up on the farm.
    eng.step(600)
    assert farm.vegetables_stored > initial
    # And no grain should accumulate — this isn't a wheat farm anymore.
    assert farm.grain_stored == 0.0


def test_vegetables_transport_to_warehouse():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=0.0, grain_stocked=0.0)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    eng.submit(SetFarmCrop(building_id=farm.id, crop=int(Crop.VEGETABLES)))
    # Find any clear tile near the farm (within transport reach) for the
    # warehouse — neighbors of the farm may already hold other starter
    # buildings.
    wh_xy = None
    for radius in range(1, 6):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                nx, ny = farm.x + dx, farm.y + dy
                if not city.in_bounds(nx, ny):
                    continue
                t = city.tile(nx, ny)
                if t.building_id == -1 and t.terrain in (CityTerrain.GRASS, CityTerrain.DIRT):
                    wh_xy = (nx, ny)
                    break
            if wh_xy:
                break
        if wh_xy:
            break
    assert wh_xy is not None
    eng.submit(PlaceZone(x=wh_xy[0], y=wh_xy[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    # Seed some veg on the farm so transport has something to ship.
    farm.vegetables_stored = 100.0
    initial_wh = warehouse.vegetables_stored
    initial_farm = farm.vegetables_stored
    eng.step(50)
    assert warehouse.vegetables_stored > initial_wh
    assert farm.vegetables_stored < initial_farm


def test_pleb_meal_drains_warehouse_when_only_veg_in_reach():
    """If the only food source in reach has vegetables (granary empty
    or absent), plebs draw from the warehouse and don't starve."""
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=0.0)
    # Strip the house's link to the granary by emptying the granary
    # entirely; plebs would normally starve. Add a warehouse with veg.
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.grain_stored = 0.0
    house = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    # Find an open tile near the house for a warehouse so coverage hits.
    wh_xy = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0)):
        nx, ny = house.x + dx, house.y + dy
        if not city.in_bounds(nx, ny):
            continue
        t = city.tile(nx, ny)
        if t.building_id == -1 and t.terrain in (CityTerrain.GRASS, CityTerrain.DIRT):
            wh_xy = (nx, ny)
            break
    assert wh_xy is not None
    eng.submit(PlaceZone(x=wh_xy[0], y=wh_xy[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    warehouse.vegetables_stored = 500.0
    veg_before = warehouse.vegetables_stored
    # Step until the next pleb meal tick fires.
    while state.tick % 24 != 5:
        eng.step(1)
    eng.step(1)  # tick lands on 6 (offset for pleb meal)
    assert warehouse.vegetables_stored < veg_before


def test_pleb_meal_splits_when_both_food_types_in_reach():
    """When both grain (granary) and veg (warehouse) are in reach with
    stock, a pleb meal tick should drain both sources."""
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=1000.0)
    house = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    wh_xy = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0)):
        nx, ny = house.x + dx, house.y + dy
        if not city.in_bounds(nx, ny):
            continue
        t = city.tile(nx, ny)
        if t.building_id == -1 and t.terrain in (CityTerrain.GRASS, CityTerrain.DIRT):
            wh_xy = (nx, ny)
            break
    assert wh_xy is not None
    eng.submit(PlaceZone(x=wh_xy[0], y=wh_xy[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
    warehouse.completion = 1.0
    warehouse.vegetables_stored = 500.0
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    grain_before = granary.grain_stored
    veg_before = warehouse.vegetables_stored
    while state.tick % 24 != 5:
        eng.step(1)
    eng.step(1)
    assert granary.grain_stored < grain_before
    assert warehouse.vegetables_stored < veg_before


def test_variety_bonus_outpaces_grain_only():
    """Two parallel cities with the same starting setup — one with
    only grain in reach, one with both grain and vegetables. After the
    same wall-clock window, the variety setup should have higher
    satisfaction."""
    def setup(with_veg: bool):
        state = new_game(seed=42)
        eng = Engine(state, default_systems())
        city = state.player_city()
        bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=10_000.0)
        if with_veg:
            house = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
            wh_xy = None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0)):
                nx, ny = house.x + dx, house.y + dy
                if not city.in_bounds(nx, ny):
                    continue
                t = city.tile(nx, ny)
                if t.building_id == -1 and t.terrain in (CityTerrain.GRASS, CityTerrain.DIRT):
                    wh_xy = (nx, ny)
                    break
            assert wh_xy is not None
            eng.submit(PlaceZone(x=wh_xy[0], y=wh_xy[1], kind=ZoneKind.WAREHOUSE))
            eng.step(1)
            warehouse = next(b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE)
            warehouse.completion = 1.0
            warehouse.vegetables_stored = 10_000.0
        # Reset satisfaction to a low value so the per-meal bonus moves
        # the needle.
        city.districts[0].satisfaction = 0.2
        return eng, city

    eng_grain, city_grain = setup(with_veg=False)
    eng_both, city_both = setup(with_veg=True)
    # Run for two weeks of pleb meals (14 daily meals).
    eng_grain.step(24 * 14)
    eng_both.step(24 * 14)
    assert (
        city_both.districts[0].satisfaction
        > city_grain.districts[0].satisfaction
    )


def test_treasury_vegetables_aggregates_warehouse_stocks():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Designate two warehouses; hand-finish + seed.
    spot_a = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot_a[0], y=spot_a[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    spot_b = find_clear_grass(city, exclude={spot_a})
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    eng.submit(PlaceZone(x=spot_b[0], y=spot_b[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    warehouses = [b for b in city.buildings if b.kind == BuildingKind.WAREHOUSE]
    assert len(warehouses) == 2
    for w in warehouses:
        w.completion = 1.0
    warehouses[0].vegetables_stored = 120.0
    warehouses[1].vegetables_stored = 80.0
    _sync_treasury_vegetables(city)
    assert city.treasury.vegetables == 200.0
