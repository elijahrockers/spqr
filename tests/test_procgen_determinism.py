from spqr.bootstrap import new_game
from spqr.persistence import encode_bytes


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
    assert len(city.buildings) >= 5
    assert len(city.districts) == 1
    kinds = {s.kind for s in state.province.sites}
    from spqr.sim.models import SiteKind
    assert SiteKind.PLAYER_CITY in kinds
