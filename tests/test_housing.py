"""Tests for the SimCity-style fresh start: empty terrain, zero pop,
RESIDENCE designation = immediate tier-0 plot, migration gated on
housing capacity, road-amenity tier upgrades that require timber for
huts and timber+stone for cottages/insulae."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, SetFarmCrop, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH, HOURS_PER_WEEK
from spqr.sim.models import (
    RESIDENCE_TIER_CAPACITY,
    RESIDENCE_TIER_UPGRADE_STONE_COST,
    RESIDENCE_TIER_UPGRADE_TIMBER_COST,
    BuildingKind,
    CityTerrain,
    Crop,
    farm_worker_slots,
)
from spqr.sim.systems import default_systems

from ._helpers import bootstrap_starter_city, find_clear_grass


def test_no_seeded_buildings_at_start():
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    assert len(city.buildings) == 0


def test_zero_population_at_start():
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    assert city.districts[0].pops.total() == 0


def test_residence_designation_completes_immediately():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    res = city.buildings[-1]
    assert res.kind == BuildingKind.RESIDENCE
    assert res.completion >= 1.0
    assert res.tier == 0


def test_undeveloped_residence_houses_three_plebs():
    """Tier-0 residences are squatter family lots — capacity is 3 now."""
    assert RESIDENCE_TIER_CAPACITY[0] == 3


def test_migration_fills_residence_when_food_present():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=0.0, grain_stocked=50_000.0)
    d = city.districts[0]
    d.satisfaction = 0.95
    eng.step(HOURS_PER_WEEK * 8)
    assert d.pops.plebs > 0
    assert d.pops.plebs <= RESIDENCE_TIER_CAPACITY[0] + 0.5


def test_no_migration_when_no_housing():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    d = city.districts[0]
    d.satisfaction = 0.95
    eng.step(HOURS_PER_MONTH * 6)
    assert d.pops.plebs == 0


def _designate_with_adjacent_road(eng, city):
    """Helper: find a clear grass tile with a clear-grass neighbor to
    the east, place a residence + adjacent road, return both."""
    res_xy = None
    for y in range(1, city.height - 1):
        for x in range(1, city.width - 1):
            here = city.tile(x, y)
            east = city.tile(x + 1, y)
            if (
                here.building_id == -1
                and here.terrain == CityTerrain.GRASS
                and east.building_id == -1
                and east.terrain == CityTerrain.GRASS
            ):
                res_xy = (x, y)
                break
        if res_xy:
            break
    assert res_xy is not None
    eng.submit(PlaceZone(x=res_xy[0], y=res_xy[1], kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=res_xy[0] + 1, y=res_xy[1], kind=ZoneKind.ROAD))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    road = next(b for b in city.buildings if b.kind == BuildingKind.ROAD)
    road.completion = 1.0
    return res, road


def test_residence_upgrades_to_tier1_with_road_and_timber():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 100.0
    city.treasury.stone = 100.0
    res, _road = _designate_with_adjacent_road(eng, city)
    timber_before = city.treasury.timber
    eng.step(HOURS_PER_MONTH)
    assert res.tier == 1
    assert city.treasury.timber == timber_before - RESIDENCE_TIER_UPGRADE_TIMBER_COST[1]


def test_residence_does_not_upgrade_without_road():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    city.treasury.timber = 100.0
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    eng.step(HOURS_PER_MONTH)
    assert res.tier == 0


def test_cottages_require_stone():
    """Tier 2 (cottages) needs both timber AND stone — set timber but
    no stone, confirm the tier-1→2 upgrade halts at 1."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0   # ample for tier 1 + tier 2 timber
    # Just enough stone for the road designation (cost: 2). After the
    # road is built, no stone remains, so the cottage upgrade (which
    # needs 10) should halt at tier 1.
    city.treasury.stone = 2.0
    res, _road = _designate_with_adjacent_road(eng, city)
    assert city.treasury.stone == 0.0  # road consumed it
    # Run two months: first month upgrades to tier 1 (huts), second
    # would attempt tier 2 (cottages) but should fail without stone.
    eng.step(HOURS_PER_MONTH * 2)
    assert res.tier == 1


def test_cottages_upgrade_when_stone_available():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    res, _road = _designate_with_adjacent_road(eng, city)
    # Two months: tier 1 then tier 2.
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    eng.step(HOURS_PER_MONTH * 2)
    assert res.tier == 2
    timber_spent = (
        RESIDENCE_TIER_UPGRADE_TIMBER_COST[1]
        + RESIDENCE_TIER_UPGRADE_TIMBER_COST[2]
    )
    stone_spent = (
        RESIDENCE_TIER_UPGRADE_STONE_COST[1]
        + RESIDENCE_TIER_UPGRADE_STONE_COST[2]
    )
    assert city.treasury.timber == timber_before - timber_spent
    assert city.treasury.stone == stone_before - stone_spent


def test_new_farm_defaults_to_wheat_with_one_worker_slot():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    eng.step(1)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    assert farm.crop == int(Crop.WHEAT)
    assert farm_worker_slots(farm) == 1


def test_set_farm_crop_switches_and_resets_maturity():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    eng.step(1)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    farm.completion = 1.0
    farm.grain_maturity = 0.5
    eng.submit(SetFarmCrop(building_id=farm.id, crop=int(Crop.VEGETABLES)))
    eng.step(1)
    assert farm.crop == int(Crop.VEGETABLES)
    assert farm.grain_maturity == 0.0
    assert farm_worker_slots(farm) == 4


def test_vegetables_farm_does_not_produce_grain():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    bootstrap_starter_city(state, eng, plebs=50.0, grain_stocked=0.0)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    eng.submit(SetFarmCrop(building_id=farm.id, crop=int(Crop.VEGETABLES)))
    while True:
        _, m, _ = state.date()
        if m == 6:
            break
        eng.step(1)
    farm.grain_maturity = 0.0
    eng.step(HOURS_PER_MONTH)
    assert farm.grain_maturity == 0.0
