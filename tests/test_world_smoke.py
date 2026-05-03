"""End-to-end sanity: a fresh world runs a full game-year without crashing,
the simulation produces non-trivial events, and the state remains coherent."""

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_YEAR
from spqr.sim.systems import default_systems

from ._helpers import bootstrap_starter_city, find_clear_grass


def test_runs_one_full_year_without_crashing():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    # Drop in the minimal starter set so migration has somewhere to land
    # and can be fed; otherwise pop stays at 0 by design. The bootstrap
    # itself burns one tick to apply its PlaceZone commands.
    bootstrap_starter_city(state, eng)
    eng.step(HOURS_PER_YEAR)
    assert state.tick >= HOURS_PER_YEAR
    city = state.player_city()
    pops = sum(d.pops.total() for d in city.districts)
    assert pops > 0, "city must not be empty after a year"
    # Treasury floors at 0 — never goes negative regardless of disasters.
    assert city.treasury.grain >= 0.0
    assert city.treasury.denarii >= 0.0
    # The log should have grown (founding entry plus monthly events).
    assert len(state.log) >= 1


def test_buildings_under_construction_complete_within_two_weeks():
    from spqr.engine.commands import PlaceZone, ZoneKind

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Construction needs labor — seed pleb pop directly so the test
    # isolates construction mechanics from migration timing.
    city.districts[0].pops.plebs = 50.0
    target = find_clear_grass(city)
    eng.submit(PlaceZone(x=target[0], y=target[1], kind=ZoneKind.WORKSHOP))
    eng.step(1)
    new_b = city.buildings[-1]
    assert new_b.completion < 1.0
    eng.step(24 * 14)  # two game weeks
    assert new_b.completion >= 1.0
