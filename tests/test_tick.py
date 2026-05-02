from spqr.bootstrap import new_game
from spqr.engine.commands import (
    PlaceZone,
    PlaceZoneRect,
    SetSpeed,
    TogglePause,
    ZoneKind,
)
from spqr.engine.tick import Engine, is_buildable
from spqr.engine.world import Speed
from spqr.sim.models import BuildingKind, CityTerrain
from spqr.sim.systems import default_systems


def test_step_advances_tick_count():
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    assert state.tick == 0
    eng.step(10)
    assert state.tick == 10


def test_pause_command_changes_speed():
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    assert state.speed == Speed.NORMAL
    eng.submit(TogglePause())
    eng.step(1)
    assert state.speed == Speed.PAUSED
    eng.submit(TogglePause())
    eng.step(1)
    assert state.speed == Speed.NORMAL


def test_set_speed_clamps():
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    eng.submit(SetSpeed(99))
    eng.step(1)
    assert state.speed == Speed.FASTEST
    eng.submit(SetSpeed(-5))
    eng.step(1)
    assert state.speed == Speed.PAUSED


def test_place_zone_rect_only_fills_buildable_empty_tiles():
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Grant unlimited treasury so the test isolates the buildability check.
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0

    # Pick a sub-rectangle and count how many tiles are buildable+empty.
    x1, y1, x2, y2 = 5, 3, 14, 8
    n_buildable = 0
    occupied_or_unbuildable = 0
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain in (CityTerrain.GRASS, CityTerrain.DIRT):
                n_buildable += 1
            else:
                occupied_or_unbuildable += 1

    n_before = len(city.buildings)
    eng.submit(PlaceZoneRect(x1=x1, y1=y1, x2=x2, y2=y2, kind=ZoneKind.FARM))
    eng.step(1)
    placed = len(city.buildings) - n_before
    assert placed == n_buildable, (
        f"expected {n_buildable} placements, got {placed} "
        f"(skipped {occupied_or_unbuildable} unbuildable/occupied tiles)"
    )
    # Every newly placed building should sit on a buildable terrain and
    # be assigned to district 0.
    for b in city.buildings[n_before:]:
        assert b.kind == BuildingKind.FARM
        assert b.completion < 1.0
        assert b.id in city.districts[0].building_ids


def test_place_zone_rect_skips_unaffordable_tiles():
    """Treasury-bounded partial placement: only as many tiles as the city
    can afford get designated; the rest are skipped with a warning."""
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Cap timber so only 3 farms (3 * 10 = 30) can be afforded.
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 30.0
    city.treasury.stone = 0.0

    n_before = len(city.buildings)
    eng.submit(PlaceZoneRect(x1=5, y1=3, x2=14, y2=8, kind=ZoneKind.FARM))
    eng.step(1)
    placed = len(city.buildings) - n_before
    assert placed == 3
    assert city.treasury.timber == 0.0
    assert city.treasury.denarii == 10_000.0 - 3 * 20


def test_place_zone_debits_treasury():
    state = new_game(seed=2)
    eng = Engine(state, default_systems())
    city = state.player_city()
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone

    # Find an empty grass tile.
    spot = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                spot = (x, y)
                break
        if spot:
            break
    assert spot is not None
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    # Warehouse cost: 80d / 20t / 20s.
    assert city.treasury.denarii == den_before - 80
    assert city.treasury.timber == timber_before - 20
    assert city.treasury.stone == stone_before - 20


def test_construction_stalls_without_workforce():
    state = new_game(seed=3)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Drain pop so there are no workers left after operational allocation.
    for d in city.districts:
        d.pops.plebs = 0.0
    # Find empty grass to designate.
    spot = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                spot = (x, y)
                break
        if spot:
            break
    assert spot is not None
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    eng.step(50)
    new_b = city.buildings[-1]
    # No labor → completion stays at 0.
    assert new_b.completion == 0.0
    assert new_b.workers_assigned == 0


def test_construction_uses_builder_slots_and_advances():
    state = new_game(seed=4)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # FARM has 1 builder slot, 168 build-hours; with 1 builder, completes at 168.
    spot = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                spot = (x, y)
                break
        if spot:
            break
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    # 168 build-hours with 1 builder; one extra tick to absorb fp drift.
    eng.step(170)
    new_b = city.buildings[-1]
    assert new_b.completion >= 1.0


def test_total_storage_capacity_grows_when_warehouse_completes():
    from spqr.engine.tick import total_storage_capacity

    state = new_game(seed=5)
    city = state.player_city()
    # Starter buildings: forum (100) is the only storage-bearing.
    base_cap = total_storage_capacity(city)
    assert base_cap == 100
    eng = Engine(state, default_systems())
    # Find empty spot and grant materials.
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    spot = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                spot = (x, y)
                break
        if spot:
            break
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WAREHOUSE))
    eng.step(1)
    # Still under construction — capacity unchanged.
    assert total_storage_capacity(city) == base_cap
    eng.step(400)
    # Now completed; capacity should have grown by 250.
    assert total_storage_capacity(city) == base_cap + 250


def test_place_zone_rect_normalizes_corners():
    state = new_game(seed=2)
    eng = Engine(state, default_systems())
    city = state.player_city()
    n_before = len(city.buildings)
    # Pass corners in reversed order — the engine should normalize.
    eng.submit(PlaceZoneRect(x1=20, y1=15, x2=18, y2=13, kind=ZoneKind.WORKSHOP))
    eng.step(1)
    placed_a = len(city.buildings) - n_before
    # And again with the canonical order.
    state2 = new_game(seed=2)
    eng2 = Engine(state2, default_systems())
    n_before2 = len(state2.player_city().buildings)
    eng2.submit(PlaceZoneRect(x1=18, y1=13, x2=20, y2=15, kind=ZoneKind.WORKSHOP))
    eng2.step(1)
    placed_b = len(state2.player_city().buildings) - n_before2
    assert placed_a == placed_b


def test_is_buildable_rejects_water_and_buildings():
    state = new_game(seed=3)
    city = state.player_city()
    # Find a water tile and a building-occupied tile and confirm both reject.
    water = next(
        (
            (x, y)
            for y in range(city.height)
            for x in range(city.width)
            if city.tile(x, y).terrain == CityTerrain.WATER
        ),
        None,
    )
    if water is not None:
        assert not is_buildable(city, water[0], water[1])
    occupied = next(
        (
            (b.x, b.y)
            for b in city.buildings
        ),
        None,
    )
    assert occupied is not None
    assert not is_buildable(city, occupied[0], occupied[1])


def test_place_zone_creates_building():
    state = new_game(seed=1)
    eng = Engine(state, default_systems())
    city = state.player_city()
    n_before = len(city.buildings)
    # Find an empty grass tile to place on.
    empty: tuple[int, int] | None = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain.name == "GRASS":
                empty = (x, y)
                break
        if empty:
            break
    assert empty is not None
    eng.submit(PlaceZone(x=empty[0], y=empty[1], kind=ZoneKind.FARM))
    eng.step(1)
    assert len(city.buildings) == n_before + 1
    new_b = city.buildings[-1]
    assert new_b.kind == BuildingKind.FARM
    assert new_b.completion < 1.0  # newly designated, under construction
