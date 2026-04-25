from __future__ import annotations

import enum

import msgspec


class CitizenRole(enum.IntEnum):
    MAGISTRATE = 0
    CENTURION = 1
    MERCHANT = 2
    PRIEST = 3
    AGITATOR = 4


class Citizen(msgspec.Struct, frozen=False):
    id: int
    name: str
    role: CitizenRole
    age: int
    # Traits in [-1.0, 1.0]; influence simulation outcomes via systems.
    ambition: float = 0.0
    competence: float = 0.0
    piety: float = 0.0
    # Tick at which the citizen entered their current role; used for retirement,
    # term limits, and narrative logging.
    role_since_tick: int = 0
