from __future__ import annotations

import msgspec

from .population import PopPool


class District(msgspec.Struct, frozen=False):
    """A logical neighborhood within a city: shares a pop pool, satisfaction
    state, and a list of building ids assigned to it."""

    id: int
    name: str
    pops: PopPool
    building_ids: list[int] = msgspec.field(default_factory=list)
    # Satisfaction in 0.0 .. 1.0; drives migration in/out and unrest accrual.
    satisfaction: float = 0.5
