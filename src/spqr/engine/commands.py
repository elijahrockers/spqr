from __future__ import annotations

import enum
from dataclasses import dataclass


class ZoneKind(enum.IntEnum):
    """Player-placeable zones — a subset of BuildingKind that the user can
    designate. Construction systems will fill these out over time."""
    FARM = 0
    RESIDENCE = 1
    GRANARY = 2
    WORKSHOP = 3
    ROAD = 4
    WAREHOUSE = 5
    LUMBER_MILL = 6
    QUARRY = 7


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


@dataclass(slots=True)
class SetFarmCrop:
    """Change a farm's crop. crop is a Crop IntEnum value (0=WHEAT,
    1=VEGETABLES). No-op if the building isn't a FARM."""
    building_id: int
    crop: int


Command = (
    TogglePause
    | SetSpeed
    | PlaceZone
    | PlaceZoneRect
    | SetTaxRate
    | SetGrainDole
    | SetFarmCrop
)
