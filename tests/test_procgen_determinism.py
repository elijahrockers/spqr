from collections import Counter

from spqr.bootstrap import new_game
from spqr.persistence import encode_bytes
from spqr.sim.models import BuildingKind, SiteKind


def test_same_seed_yields_same_state():
    a = encode_bytes(new_game(seed=42))
    b = encode_bytes(new_game(seed=42))
    assert a == b


def test_different_seeds_diverge():
    a = encode_bytes(new_game(seed=1))
    b = encode_bytes(new_game(seed=2))
    assert a != b


def test_generated_world_has_player_city():
    state = new_game(seed=42)
    city = state.player_city()
    assert city.name
    assert len(city.districts) == 1
    assert city.districts[0].pops.total() == 0
    kinds = {s.kind for s in state.province.sites}
    assert SiteKind.PLAYER_CITY in kinds


def test_default_seed_drops_starter_block():
    """The production default is to seed a compact starter layout: 6
    farms, 3 residences, 1 granary, 1 warehouse, 1 lumber mill, plus
    6 road tiles connecting them."""
    state = new_game(seed=42)
    city = state.player_city()
    counts = Counter(b.kind for b in city.buildings)
    assert counts[BuildingKind.FARM] == 6
    assert counts[BuildingKind.RESIDENCE] == 3
    assert counts[BuildingKind.GRANARY] == 1
    assert counts[BuildingKind.WAREHOUSE] == 1
    assert counts[BuildingKind.LUMBER_MILL] == 1
    assert counts[BuildingKind.ROAD] == 6
    # All seeded buildings start operational so the player can use them
    # immediately.
    for b in city.buildings:
        assert b.completion >= 1.0
    # Layout is compact: every seeded building sits within a 6×3 area.
    xs = [b.x for b in city.buildings]
    ys = [b.y for b in city.buildings]
    assert max(xs) - min(xs) <= 5
    assert max(ys) - min(ys) <= 2


def test_seed_starter_false_leaves_blank_map():
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    assert len(city.buildings) == 0
