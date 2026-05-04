"""Tests for the SimCity-style fresh start: empty terrain, zero pop,
RESIDENCE designation = immediate tier-0 plot, migration gated on
housing capacity, road-amenity tier upgrades that require timber for
huts and timber+stone for cottages/insulae."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import (
    PlaceZone,
    SetFarmCrop,
    SetResidenceTierCap,
    ZoneKind,
)
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH, HOURS_PER_WEEK
from spqr.sim.models import (
    RESIDENCE_MAX_TIER,
    RESIDENCE_TIER_CAPACITY,
    RESIDENCE_TIER_UPGRADE_STONE_COST,
    RESIDENCE_TIER_UPGRADE_TIMBER_COST,
    BuildingKind,
    CityTerrain,
    Crop,
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


def test_undeveloped_residence_houses_two_plebs():
    """Tier-0 residences are squatter family lots — capacity is 2."""
    assert RESIDENCE_TIER_CAPACITY[0] == 2


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
    """Helper: find a row of clear grass at least 4 tiles wide with a
    clear row beneath (for office 2×2 footprint extensions used by
    callers that add an office east of the road). Place a residence +
    adjacent road, return both."""
    res_xy = None
    for y in range(1, city.height - 2):
        for x in range(1, city.width - 4):
            here_clear = all(
                city.tile(x + dx, y).building_id == -1
                and city.tile(x + dx, y).terrain == CityTerrain.GRASS
                for dx in range(4)
            )
            below_clear = all(
                city.tile(x + dx, y + 1).building_id == -1
                and city.tile(x + dx, y + 1).terrain == CityTerrain.GRASS
                for dx in range(4)
            )
            if here_clear and below_clear:
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
    """With timber, stone, furniture, road, AND a staffed office in
    reach, the residence upgrades to cottages within two months. The
    office requirement is the cottage gate; furniture is the workshop-
    fed amenity gate (tier 2 onward)."""
    from spqr.sim.models import RESIDENCE_TIER_UPGRADE_FURNITURE_COST

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 100.0  # cottages need 50; have headroom
    res, road = _designate_with_adjacent_road(eng, city)
    # Office two tiles east of the road, so its reach covers the
    # residence (road extends Dijkstra reach cheaply).
    eng.submit(PlaceZone(x=road.x + 1, y=road.y, kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 3
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    furniture_before = city.treasury.furniture
    # Two months: tier 1 then tier 2.
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
    furniture_spent = (
        RESIDENCE_TIER_UPGRADE_FURNITURE_COST[1]
        + RESIDENCE_TIER_UPGRADE_FURNITURE_COST[2]
    )
    assert city.treasury.timber == timber_before - timber_spent
    assert city.treasury.stone == stone_before - stone_spent
    assert city.treasury.furniture == furniture_before - furniture_spent


def test_new_farm_defaults_to_wheat_with_three_worker_slots():
    """Wheat farms now scale up to 3 workers (was 1). Frequency-only
    yield scaling: more workers means more harvests per year, same
    yield per harvest."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    eng.step(1)
    farm = next(b for b in city.buildings if b.kind == BuildingKind.FARM)
    assert farm.crop == int(Crop.WHEAT)
    assert farm.farm_worker_slots() == 3


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
    # Both crops cap at 3 workers now (uniform farm cap).
    assert farm.farm_worker_slots() == 3


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
    farm.grain_stored = 0.0
    grain_treasury_before = city.treasury.grain
    eng.step(HOURS_PER_MONTH)
    # The farm is sown with vegetables, so it must not contribute any
    # grain — neither to the on-farm buffer nor (via cart) to the
    # treasury. (Vegetables produced this month may have been drained
    # by plebs via the eat-from-farms fallback, since the bootstrap has
    # no warehouse and an empty granary, so we don't assert on
    # vegetables_stored here.)
    assert farm.grain_stored == 0.0
    assert city.treasury.grain == grain_treasury_before


def test_road_within_2_tiles_buffs_district_satisfaction():
    """A residence with a road within Chebyshev distance 2 contributes
    a per-month satisfaction bump. With a single residence and a single
    road tile, the fraction-with-road is 1.0, so the full
    ROAD_DESIRABILITY_BONUS_PER_MONTH lands.

    Calls the housing helper directly so meal/migration noise can't
    drown out the bonus — this is a unit test of the helper's math."""
    from spqr.sim.models import ROAD_DESIRABILITY_BONUS_PER_MONTH
    from spqr.sim.systems.housing import _apply_road_desirability

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    res, _road = _designate_with_adjacent_road(eng, city)
    d = city.districts[0]
    d.satisfaction = 0.5
    _apply_road_desirability(city)
    delta = d.satisfaction - 0.5
    assert abs(delta - ROAD_DESIRABILITY_BONUS_PER_MONTH) < 1e-6


def test_no_road_means_no_desirability_buff():
    """Residence without a road in 2 tiles: zero contribution to the
    road desirability bonus."""
    from spqr.sim.systems.housing import _apply_road_desirability

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    d = city.districts[0]
    d.satisfaction = 0.5
    _apply_road_desirability(city)
    assert d.satisfaction == 0.5


def test_road_buff_scales_with_fraction_of_residences_in_reach():
    """One residence near a road, one far away. Fraction = 0.5, so the
    monthly bump should be half of the full bonus."""
    from spqr.sim.models import ROAD_DESIRABILITY_BONUS_PER_MONTH
    from spqr.sim.systems.housing import _apply_road_desirability

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    res_a, _road = _designate_with_adjacent_road(eng, city)
    used = {(res_a.x, res_a.y), (res_a.x + 1, res_a.y)}
    far_xy = None
    for y in range(city.height):
        for x in range(city.width):
            if (x, y) in used:
                continue
            if abs(x - res_a.x) < 5 or abs(y - res_a.y) < 5:
                continue
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                far_xy = (x, y)
                break
        if far_xy:
            break
    assert far_xy is not None
    eng.submit(PlaceZone(x=far_xy[0], y=far_xy[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    d = city.districts[0]
    d.satisfaction = 0.5
    _apply_road_desirability(city)
    delta = d.satisfaction - 0.5
    expected = ROAD_DESIRABILITY_BONUS_PER_MONTH * 0.5
    assert abs(delta - expected) < 1e-6


# --- Tier-cap configuration ------------------------------------------------

def test_new_residence_defaults_to_uncapped():
    """Newly-designated residences should default to tier_cap =
    RESIDENCE_MAX_TIER, i.e. no upgrade ceiling."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    assert res.tier_cap == RESIDENCE_MAX_TIER


def test_set_residence_tier_cap_command_clamps_and_applies():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    res = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    eng.submit(SetResidenceTierCap(building_id=res.id, tier_cap=1))
    eng.step(1)
    assert res.tier_cap == 1
    # Out-of-range values clamp to [0, RESIDENCE_MAX_TIER].
    eng.submit(SetResidenceTierCap(building_id=res.id, tier_cap=99))
    eng.step(1)
    assert res.tier_cap == RESIDENCE_MAX_TIER
    eng.submit(SetResidenceTierCap(building_id=res.id, tier_cap=-5))
    eng.step(1)
    assert res.tier_cap == 0


def test_set_residence_tier_cap_ignored_for_non_residence():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.tier_cap = RESIDENCE_MAX_TIER  # baseline
    eng.submit(SetResidenceTierCap(building_id=farm.id, tier_cap=1))
    eng.step(1)
    # Farm's tier_cap stays at the default — command is a no-op for
    # non-residence kinds.
    assert farm.tier_cap == RESIDENCE_MAX_TIER


def test_housing_respects_tier_cap_at_huts():
    """A residence capped at tier 1 (huts) should upgrade once and then
    stop, even with materials and a road sitting around for further
    upgrades."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    res, _road = _designate_with_adjacent_road(eng, city)
    res.tier_cap = 1
    # Three months: would normally reach tier 2 by month 2 and tier 3
    # by month 3, but the cap should hold it at huts.
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier == 1


def test_housing_respects_tier_cap_at_undeveloped():
    """tier_cap = 0 freezes a residence at undeveloped — the player
    explicitly never wants this plot to densify."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    res, _road = _designate_with_adjacent_road(eng, city)
    res.tier_cap = 0
    eng.step(HOURS_PER_MONTH * 3)
    assert res.tier == 0


def test_lowering_cap_below_tier_does_not_downgrade():
    """Lowering the cap below the current tier prevents future
    upgrades but does NOT demolish existing tier — a tier-2 cottage
    capped at tier 1 stays as cottages.

    Needs a staffed office in reach so cottages are reachable in the
    first two months, and furniture in treasury for the cottage gate."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 200.0
    city.treasury.stone = 100.0
    city.treasury.furniture = 200.0  # cottages need 50; insula needs 100
    city.treasury.stoneware = 100.0  # insula needs 50
    res, road = _designate_with_adjacent_road(eng, city)
    eng.submit(PlaceZone(x=road.x + 1, y=road.y, kind=ZoneKind.OFFICE))
    eng.step(1)
    office = next(b for b in city.buildings if b.kind == BuildingKind.OFFICE)
    office.completion = 1.0
    office.workers_assigned = 3
    eng.step(HOURS_PER_MONTH * 2)  # reaches tier 2
    assert res.tier == 2
    # Now cap below current tier.
    eng.submit(SetResidenceTierCap(building_id=res.id, tier_cap=1))
    eng.step(HOURS_PER_MONTH * 2)  # would otherwise reach tier 3
    assert res.tier == 2  # unchanged: no downgrade, no further upgrade
