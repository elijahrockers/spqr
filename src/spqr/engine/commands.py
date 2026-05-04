from __future__ import annotations

import enum
from dataclasses import dataclass


class ZoneKind(enum.IntEnum):
    """Player-placeable zones — a subset of BuildingKind that the user
    can designate, plus BULLDOZE which removes buildings instead."""
    FARM = 0
    RESIDENCE = 1
    GRANARY = 2
    WORKSHOP = 3
    ROAD = 4
    WAREHOUSE = 5
    LUMBER_MILL = 6
    QUARRY = 7
    OFFICE = 8
    BULLDOZE = 10        # remove building; free if under construction, 10d if completed


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


@dataclass(slots=True)
class SetResidenceTierCap:
    """Cap a residence's auto-upgrade ceiling. tier_cap is in 0..3
    (RESIDENCE_MAX_TIER). The housing system stops upgrading the
    residence once `tier == tier_cap`, even if materials and roads
    would otherwise advance it. No-op if the building isn't a
    RESIDENCE. Lowering the cap below the current tier is allowed but
    does NOT downgrade — it just prevents future upgrades."""
    building_id: int
    tier_cap: int


@dataclass(slots=True)
class SetWorkshopGood:
    """Change a workshop's good. good is a Good IntEnum value
    (0=FURNITURE, 1=STONEWARE). No-op if the building isn't a
    WORKSHOP. Switching is instant — workshops have no in-progress
    batch state to discard."""
    building_id: int
    good: int


@dataclass(slots=True)
class SetLaborPriority:
    """Replace the player city's labor_priority list. `priority` must
    be a permutation of LaborCategory values 0..5 (one entry per
    bucket). Invalid input is silently dropped by the handler — the
    UI never produces invalid input; this is a defense-in-depth gate
    for replays / future load paths."""
    priority: list[int]


@dataclass(slots=True)
class SetWarehouseCaps:
    """Set a warehouse's per-good capacity allocation. Each value is
    the cap for that good in this warehouse; the sum must be
    <= WAREHOUSE_TOTAL_CAPACITY and each value must be >= 0. No-op
    if the building isn't a WAREHOUSE or the caps fail validation.
    Existing stored quantities are NOT discarded if the new cap is
    below current stock — transport just stops adding more until
    inventory drains under the new cap. The five goods are timber,
    stone, vegetables, furniture, stoneware; the warehouse contributes
    each cap to the corresponding city-wide treasury cap (vegetables
    stays per-warehouse since each warehouse physically stores its
    own veg)."""
    building_id: int
    cap_timber: int
    cap_stone: int
    cap_vegetables: int
    cap_furniture: int
    cap_stoneware: int


Command = (
    TogglePause
    | SetSpeed
    | PlaceZone
    | PlaceZoneRect
    | SetTaxRate
    | SetGrainDole
    | SetFarmCrop
    | SetResidenceTierCap
    | SetWorkshopGood
    | SetLaborPriority
    | SetWarehouseCaps
)
