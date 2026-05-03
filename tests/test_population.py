from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH
from spqr.sim.systems import default_systems

from ._helpers import bootstrap_starter_city


def test_pops_grow_with_high_satisfaction():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Designate the starter set with the granary stockpiled and one HOUSE
    # in place; with high satisfaction, plebs migrate in weekly.
    bootstrap_starter_city(state, eng, plebs=0.0, grain_stocked=50_000.0)
    d = city.districts[0]
    d.satisfaction = 0.95
    initial = d.pops.plebs
    eng.step(HOURS_PER_MONTH * 3)
    assert d.pops.plebs > initial


def test_pops_shrink_on_starvation():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Seed a small pleb pool, then strip every grain source so the
    # winter starvation loop pushes pop down.
    bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=0.0)
    d = city.districts[0]
    for b in city.buildings:
        if b.kind.name == "GRANARY":
            b.grain_stored = 0.0
    initial = d.pops.plebs
    # Run two winter months. Monthly demographics with sat → 0 +
    # rising unrest shrinks the pleb pool via mortality and out-migration.
    eng.step(HOURS_PER_MONTH * 2)
    assert d.pops.plebs < initial
    assert d.pops.unrest > 0.0
    assert d.satisfaction < 0.5
