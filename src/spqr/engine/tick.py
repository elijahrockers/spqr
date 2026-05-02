from __future__ import annotations

import random
from collections.abc import Callable
from typing import Protocol

from spqr.engine.commands import (
    Command,
    PlaceZone,
    PlaceZoneRect,
    SetGrainDole,
    SetSpeed,
    SetTaxRate,
    TogglePause,
    ZoneKind,
)
from spqr.engine.events import LogSeverity, push_log
from spqr.engine.rng import RngState
from spqr.engine.world import GameState, Speed, restore_rng
from spqr.sim.models import (
    BUILDING_COST,
    STORAGE_CAPACITY,
    Building,
    BuildingKind,
    City,
    CityTerrain,
    Resources,
)


class System(Protocol):
    """A system mutates GameState in place for one tick.

    Systems must be deterministic given (state, rng): no module-level random,
    no clock reads, no I/O. The tick loop runs them in a fixed order."""
    def __call__(self, state: GameState, rng: random.Random) -> None: ...


_ZONE_TO_BUILDING: dict[ZoneKind, BuildingKind] = {
    ZoneKind.FARM: BuildingKind.FARM,
    ZoneKind.INSULA: BuildingKind.INSULA,
    ZoneKind.GRANARY: BuildingKind.GRANARY,
    ZoneKind.WORKSHOP: BuildingKind.WORKSHOP,
    ZoneKind.ROAD: BuildingKind.ROAD,
    ZoneKind.WAREHOUSE: BuildingKind.WAREHOUSE,
}

# Terrain types you can build on. Water and rock are off-limits for any
# zone; forest and hill require clearing/leveling work that's out of MVP
# scope. Roads can also lay over plain grass/dirt only.
_BUILDABLE_TERRAIN: frozenset[CityTerrain] = frozenset(
    {CityTerrain.GRASS, CityTerrain.DIRT}
)


def is_buildable(city: City, x: int, y: int) -> bool:
    """A tile is buildable if it's in bounds, empty, and on suitable terrain."""
    if not city.in_bounds(x, y):
        return False
    tile = city.tile(x, y)
    if tile.building_id != -1:
        return False
    return tile.terrain in _BUILDABLE_TERRAIN


def total_storage_capacity(city: City) -> int:
    """Sum of materials storage across all completed storage-bearing
    buildings. Determines how much timber + stone the city can hold."""
    cap = 0
    for b in city.buildings:
        if b.completion < 1.0:
            continue
        cap += STORAGE_CAPACITY.get(b.kind, 0)
    return cap


def stored_materials(city: City) -> float:
    """Combined timber + stone currently held; checked against storage cap."""
    return city.treasury.timber + city.treasury.stone


class Engine:
    """Wraps a GameState plus the live RNG, command queue, and registered
    systems. The UI layer holds an Engine and calls step() / submit()."""

    def __init__(
        self,
        state: GameState,
        systems: list[System],
        on_tick: Callable[[GameState], None] | None = None,
    ) -> None:
        self.state = state
        self.systems = systems
        self.rng = restore_rng(state)
        self._pending: list[Command] = []
        self._on_tick = on_tick

    def submit(self, cmd: Command) -> None:
        self._pending.append(cmd)

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.apply_pending()
            self.state.tick += 1
            for system in self.systems:
                system(self.state, self.rng)
            if self._on_tick is not None:
                self._on_tick(self.state)

    def capture_rng(self) -> None:
        """Persist the live RNG back into GameState so a subsequent save
        round-trips correctly."""
        self.state.rng_state = RngState.capture(self.rng)

    def apply_pending(self) -> None:
        if not self._pending:
            return
        for cmd in self._pending:
            self._apply(cmd)
        self._pending.clear()

    def _apply(self, cmd: Command) -> None:
        s = self.state
        match cmd:
            case TogglePause():
                if s.speed == Speed.PAUSED:
                    s.speed = Speed.NORMAL
                else:
                    s.speed = Speed.PAUSED
            case SetSpeed(level):
                s.speed = Speed(max(0, min(4, level)))
            case SetTaxRate(rate):
                s.player_city().tax_rate = max(0.0, min(0.5, rate))
            case SetGrainDole(per_pleb):
                s.player_city().grain_dole_per_pleb = max(0.0, per_pleb)
            case PlaceZone(x, y, kind):
                self._place_zone_rect(x, y, x, y, kind)
            case PlaceZoneRect(x1, y1, x2, y2, kind):
                self._place_zone_rect(x1, y1, x2, y2, kind)

    def _place_zone_rect(
        self, x1: int, y1: int, x2: int, y2: int, kind: ZoneKind
    ) -> None:
        city = self.state.player_city()
        b_kind = _ZONE_TO_BUILDING[kind]
        cost = BUILDING_COST[b_kind]
        x_lo, x_hi = (x1, x2) if x1 <= x2 else (x2, x1)
        y_lo, y_hi = (y1, y2) if y1 <= y2 else (y2, y1)
        district = city.districts[0] if city.districts else None
        placed = 0
        unaffordable = 0
        for y in range(y_lo, y_hi + 1):
            for x in range(x_lo, x_hi + 1):
                if not is_buildable(city, x, y):
                    continue
                if not city.treasury.can_pay(cost):
                    unaffordable += 1
                    continue
                city.treasury.pay(cost)
                building = Building(
                    id=city.next_building_id,
                    kind=b_kind,
                    x=x,
                    y=y,
                    completion=0.0,
                )
                city.next_building_id += 1
                city.buildings.append(building)
                city.tile(x, y).building_id = building.id
                if district is not None:
                    district.building_ids.append(building.id)
                placed += 1
        if placed == 0 and unaffordable == 0:
            return
        if placed == 0:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.WARNING,
                f"Cannot afford {b_kind.name.lower()}: need "
                f"{int(cost.denarii)}d {int(cost.timber)}t {int(cost.stone)}s.",
            )
            return
        if x_lo == x_hi and y_lo == y_hi:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.INFO,
                f"Designated {b_kind.name.lower()} at ({x_lo},{y_lo}).",
            )
        else:
            tail = (
                f" ({unaffordable} skipped: treasury empty)" if unaffordable else ""
            )
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.INFO,
                f"Designated {placed} {b_kind.name.lower()} tiles "
                f"in ({x_lo},{y_lo})-({x_hi},{y_hi}).{tail}",
            )
