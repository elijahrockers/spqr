"""Tests for the new furniture / stoneware tier-upgrade requirements.

Tier 2 cottages need 50 furniture (in addition to timber + stone).
Tier 3 insulae need 100 furniture and 50 stoneware. Without these
goods in the city treasury, the housing system holds the residence
back at the lower tier even when materials and gates would otherwise
allow the upgrade."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.models import (
    BuildingKind,
    CityTerrain,
    RESIDENCE_TIER_UPGRADE_FURNITURE_COST,
    RESIDENCE_TIER_UPGRADE_STONEWARE_COST,
)
from spqr.sim.systems import default_systems
from spqr.sim.systems.housing import _upgrade_residences

from ._helpers import find_clear_grass


def _setup_residence_with_road_and_office(eng, city):
    """Find a 4-tile-wide grass strip with clear row beneath. Place
    residence + adjacent road + office (so cottage office gate is
    satisfied). Hand-finish road/office and staff the office."""
    spot = None
    for y in range(1, city.height - 2):
        for x in range(1, city.width - 4):
            here = all(
                city.tile(x + dx, y).building_id == -1
                and city.tile(x + dx, y).terrain == CityTerrain.GRASS
                for dx in range(4)
            )
            below = all(
                city.tile(x + dx, y + 1).building_id == -1
                and city.tile(x + dx, y + 1).terrain == CityTerrain.GRASS
                for dx in range(4)
            )
            if here and below:
                spot = (x, y)
                break
        if spot:
            break
    assert spot is not None
    rx, ry = spot
    eng.submit(PlaceZone(x=rx, y=ry, kind=ZoneKind.RESIDENCE))
    eng.submit(PlaceZone(x=rx + 1, y=ry, kind=ZoneKind.ROAD))
    eng.submit(PlaceZone(x=rx + 2, y=ry, kind=ZoneKind.OFFICE))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    road = next(b for b in city.buildings if b.kind == BuildingKind.ROAD)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    road.completion = 1.0
    office.completion = 1.0
    office.workers_assigned = 3
    return res, road, office


def test_furniture_costs_match_design():
    """Tier 1 huts need no furniture. Tier 2 cottages need 50.
    Tier 3 insulae need 100 furniture + 50 stoneware."""
    assert RESIDENCE_TIER_UPGRADE_FURNITURE_COST[1] == 0
    assert RESIDENCE_TIER_UPGRADE_FURNITURE_COST[2] == 50
    assert RESIDENCE_TIER_UPGRADE_FURNITURE_COST[3] == 100
    assert RESIDENCE_TIER_UPGRADE_STONEWARE_COST[1] == 0
    assert RESIDENCE_TIER_UPGRADE_STONEWARE_COST[2] == 0
    assert RESIDENCE_TIER_UPGRADE_STONEWARE_COST[3] == 50


def test_cottage_upgrade_blocked_without_furniture():
    """Materials, road, office in reach — but no furniture in treasury.
    Tier 2 upgrade must fail; residence stays at huts."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    # Furniture intentionally zero.
    city.treasury.furniture = 0.0
    res, _road, _office = _setup_residence_with_road_and_office(eng, city)
    # Manually advance to huts (so the next gate is the cottage gate).
    res.tier = 1
    _upgrade_residences(state, city)
    assert res.tier == 1


def test_cottage_upgrade_succeeds_with_furniture():
    """Same setup but with 50 furniture in treasury — upgrade goes through."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 50.0
    res, _road, _office = _setup_residence_with_road_and_office(eng, city)
    res.tier = 1
    _upgrade_residences(state, city)
    assert res.tier == 2
    # Treasury was drained by the cost.
    assert city.treasury.furniture == 0.0


def test_insula_upgrade_blocked_without_stoneware():
    """Cottages in place; stone + furniture available; but no stoneware.
    Tier 3 upgrade must fail."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 200.0
    city.treasury.furniture = 200.0
    city.treasury.stoneware = 0.0
    res, _road, _office = _setup_residence_with_road_and_office(eng, city)
    res.tier = 2
    _upgrade_residences(state, city)
    assert res.tier == 2


def test_insula_upgrade_succeeds_with_stoneware_and_furniture():
    """All four resources present; tier 3 upgrade goes through."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 200.0
    city.treasury.furniture = 200.0
    city.treasury.stoneware = 50.0
    res, _road, _office = _setup_residence_with_road_and_office(eng, city)
    res.tier = 2
    _upgrade_residences(state, city)
    assert res.tier == 3
    assert city.treasury.stoneware == 0.0
    assert city.treasury.furniture == 200.0 - 100.0
