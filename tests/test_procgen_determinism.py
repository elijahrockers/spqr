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
    """The production default is to seed an 11×3 starter layout: 6
    farms, 3 residences, 1 granary, 1 warehouse, 1 lumber mill, 1
    quarry, plus 11 road tiles connecting them. The mill and quarry
    sit at the far right so residences are outside the industrial-
    nuisance radius."""
    from spqr.sim.models import INDUSTRIAL_NUISANCE_RADIUS

    state = new_game(seed=42)
    city = state.player_city()
    counts = Counter(b.kind for b in city.buildings)
    assert counts[BuildingKind.FARM] == 6
    assert counts[BuildingKind.RESIDENCE] == 3
    assert counts[BuildingKind.GRANARY] == 1
    assert counts[BuildingKind.WAREHOUSE] == 1
    assert counts[BuildingKind.LUMBER_MILL] == 1
    assert counts[BuildingKind.QUARRY] == 1
    assert counts[BuildingKind.ROAD] == 11
    # All seeded buildings start operational.
    for b in city.buildings:
        assert b.completion >= 1.0
    # Layout sits within an 11×3 area.
    xs = [b.x for b in city.buildings]
    ys = [b.y for b in city.buildings]
    assert max(xs) - min(xs) <= 10
    assert max(ys) - min(ys) <= 2
    # Crucial: every seeded residence is OUTSIDE Chebyshev distance
    # INDUSTRIAL_NUISANCE_RADIUS of every industrial building. Without
    # this gap the seeded residences would cap at huts on day one.
    residences = [b for b in city.buildings if b.kind == BuildingKind.RESIDENCE]
    industry = [
        b for b in city.buildings
        if b.kind in (BuildingKind.LUMBER_MILL, BuildingKind.QUARRY)
    ]
    for r in residences:
        for ind in industry:
            chebyshev = max(abs(r.x - ind.x), abs(r.y - ind.y))
            assert chebyshev > INDUSTRIAL_NUISANCE_RADIUS, (
                f"residence ({r.x},{r.y}) is in {ind.kind.name} "
                f"nuisance range (cheby={chebyshev})"
            )


def test_seed_starter_false_leaves_blank_map():
    state = new_game(seed=42, seed_starter=False)
    city = state.player_city()
    assert len(city.buildings) == 0
