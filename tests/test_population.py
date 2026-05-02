from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.systems import default_systems


def test_pops_grow_with_high_satisfaction():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    d = city.districts[0]
    # Force high satisfaction. Strip houses from the district and stockpile
    # every granary so meals always succeed via the `_drain_any_granary`
    # fallback — sidesteps any layout-dependent spatial-reach gaps.
    d.satisfaction = 0.95
    d.building_ids = [
        b_id for b_id in d.building_ids
        if city.buildings[b_id].kind.name not in ("INSULA", "DOMUS")
    ]
    for b in city.buildings:
        if b.kind.name == "GRANARY":
            b.grain_stored = 50_000.0
    initial = d.pops.plebs
    eng.step(HOURS_PER_MONTH * 3)
    assert d.pops.plebs > initial


def test_pops_shrink_on_starvation():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    d = city.districts[0]
    # Empty the granary at the start of January. The growing season runs
    # March-September, so during winter no farm can replenish stores —
    # this guarantees a sustained famine until spring.
    for b in city.buildings:
        if b.kind.name == "GRANARY":
            b.grain_stored = 0.0
    initial = d.pops.plebs
    # Run two winter months. Monthly demographics with sat=0 + unrest=1
    # shrinks the pleb pool via raised mortality and out-migration.
    eng.step(HOURS_PER_MONTH * 2)
    assert d.pops.plebs < initial
    assert d.pops.unrest > 0.0
    assert d.satisfaction < 0.5
