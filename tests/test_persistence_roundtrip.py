import hashlib
from pathlib import Path

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.persistence import encode_bytes, load_from_path, save_to_path
from spqr.sim.systems import default_systems


def _state_hash(state):
    return hashlib.sha256(encode_bytes(state)).hexdigest()


def test_save_load_roundtrip_state_equal(tmp_path: Path):
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    eng.step(500)
    eng.capture_rng()

    path = tmp_path / "save.spqr"
    save_to_path(state, path)
    loaded = load_from_path(path)
    assert _state_hash(state) == _state_hash(loaded)


def test_continuing_after_load_matches_uninterrupted_run(tmp_path: Path):
    state_a = new_game(seed=99)
    eng_a = Engine(state_a, default_systems())
    eng_a.step(2000)
    eng_a.capture_rng()
    hash_a = _state_hash(state_a)

    state_b = new_game(seed=99)
    eng_b = Engine(state_b, default_systems())
    eng_b.step(1000)
    eng_b.capture_rng()
    path = tmp_path / "mid.spqr"
    save_to_path(state_b, path)

    loaded = load_from_path(path)
    eng_loaded = Engine(loaded, default_systems())
    eng_loaded.step(1000)
    eng_loaded.capture_rng()
    hash_loaded = _state_hash(loaded)

    assert hash_a == hash_loaded
