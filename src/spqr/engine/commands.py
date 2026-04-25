from __future__ import annotations

import enum
from dataclasses import dataclass


class ZoneKind(enum.IntEnum):
    """Player-placeable zones — a subset of BuildingKind that the user can
    designate. Construction systems will fill these out over time."""
    FARM = 0
    INSULA = 1
    BARRACKS = 2
    GRANARY = 3
    WORKSHOP = 4
    ROAD = 5
    WAREHOUSE = 6


@dataclass(slots=True)
class TogglePause:
    pass


@dataclass(slots=True)
class SetSpeed:
    level: int


@dataclass(slots=True)
class PlaceZone:
    x: int
    y: int
    kind: ZoneKind


@dataclass(slots=True)
class PlaceZoneRect:
    """Designate every empty, buildable tile inside the bounding box for the
    given zone kind. Single-tile placement is just x1==x2, y1==y2."""
    x1: int
    y1: int
    x2: int
    y2: int
    kind: ZoneKind


@dataclass(slots=True)
class SetTaxRate:
    rate: float


@dataclass(slots=True)
class SetGrainDole:
    per_pleb: float


Command = (
    TogglePause
    | SetSpeed
    | PlaceZone
    | PlaceZoneRect
    | SetTaxRate
    | SetGrainDole
)
