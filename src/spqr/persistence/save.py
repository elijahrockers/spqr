from __future__ import annotations

import os
from pathlib import Path

import msgspec

from spqr.engine.world import GameState

from .schema import SCHEMA_VERSION


class SaveError(RuntimeError):
    pass


def save_to_path(state: GameState, path: str | os.PathLike[str]) -> None:
    """Serialize state as msgpack to `path`. Caller is responsible for first
    calling Engine.capture_rng() if the live RNG has advanced."""
    if state.schema_version != SCHEMA_VERSION:
        raise SaveError(
            f"refusing to save state with schema_version={state.schema_version} "
            f"(expected {SCHEMA_VERSION})"
        )
    blob = msgspec.msgpack.encode(state)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, p)


def load_from_path(path: str | os.PathLike[str]) -> GameState:
    blob = Path(path).read_bytes()
    state = msgspec.msgpack.decode(blob, type=GameState)
    if state.schema_version != SCHEMA_VERSION:
        raise SaveError(
            f"save schema_version={state.schema_version} does not match "
            f"current SCHEMA_VERSION={SCHEMA_VERSION}"
        )
    return state


def encode_bytes(state: GameState) -> bytes:
    return msgspec.msgpack.encode(state)


def decode_bytes(blob: bytes) -> GameState:
    return msgspec.msgpack.decode(blob, type=GameState)
