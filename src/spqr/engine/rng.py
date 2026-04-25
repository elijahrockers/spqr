from __future__ import annotations

import random

import msgspec


class RngState(msgspec.Struct, frozen=False):
    """Serializable snapshot of a `random.Random` instance.

    Why store this on GameState rather than reconstructing from a seed +
    call-count: random.Random can't fast-forward in O(1), so for long-running
    saves we capture the actual internal state."""

    version: int
    state: list[int]
    gauss_next: float | None

    @classmethod
    def capture(cls, rng: random.Random) -> "RngState":
        version, internal, gauss_next = rng.getstate()
        return cls(version=version, state=list(internal), gauss_next=gauss_next)

    def restore(self) -> random.Random:
        rng = random.Random()
        rng.setstate((self.version, tuple(self.state), self.gauss_next))
        return rng


def make_rng(seed: int) -> random.Random:
    return random.Random(seed)
