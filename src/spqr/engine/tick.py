from __future__ import annotations

import random
from collections.abc import Callable
from typing import Protocol

from spqr.engine.commands import (
    Command,
    PlaceZone,
    PlaceZoneRect,
    SetFarmCrop,
    SetGrainDole,
    SetResidenceTierCap,
    SetSpeed,
    SetTaxRate,
    SetWorkshopGood,
    TogglePause,
    ZoneKind,
)
from spqr.engine.events import LogSeverity, push_log
from spqr.engine.rng import RngState
from spqr.engine.world import GameState, Speed, restore_rng
from spqr.sim.models import (
    BUILDING_COST,
    Building,
    BuildingKind,
)


class System(Protocol):
    """A system mutates GameState in place for one tick.

    Systems must be deterministic given (state, rng): no module-level random,
    no clock reads, no I/O. The tick loop runs them in a fixed order."""
    def __call__(self, state: GameState, rng: random.Random) -> None: ...


_ZONE_TO_BUILDING: dict[ZoneKind, BuildingKind] = {
    ZoneKind.FARM: BuildingKind.FARM,
    ZoneKind.RESIDENCE: BuildingKind.RESIDENCE,
    ZoneKind.LUMBER_MILL: BuildingKind.LUMBER_MILL,
    ZoneKind.QUARRY: BuildingKind.QUARRY,
    ZoneKind.GRANARY: BuildingKind.GRANARY,
    ZoneKind.WORKSHOP: BuildingKind.WORKSHOP,
    ZoneKind.ROAD: BuildingKind.ROAD,
    ZoneKind.WAREHOUSE: BuildingKind.WAREHOUSE,
    ZoneKind.OFFICE: BuildingKind.OFFICE,
}


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
            case SetFarmCrop(building_id, crop):
                self._set_farm_crop(building_id, crop)
            case SetResidenceTierCap(building_id, tier_cap):
                self._set_residence_tier_cap(building_id, tier_cap)
            case SetWorkshopGood(building_id, good):
                self._set_workshop_good(building_id, good)

    def _set_residence_tier_cap(self, building_id: int, tier_cap: int) -> None:
        from spqr.sim.models import RESIDENCE_MAX_TIER, RESIDENCE_TIER_NAME

        city = self.state.player_city()
        if not (0 <= building_id < len(city.buildings)):
            return
        b = city.buildings[building_id]
        if b.kind != BuildingKind.RESIDENCE:
            return
        new_cap = max(0, min(RESIDENCE_MAX_TIER, tier_cap))
        if b.tier_cap == new_cap:
            return
        b.tier_cap = new_cap
        cap_name = RESIDENCE_TIER_NAME.get(new_cap, str(new_cap))
        push_log(
            self.state.log,
            self.state.tick,
            LogSeverity.INFO,
            f"Residence at ({b.x},{b.y}) capped at {cap_name}.",
        )

    def _set_workshop_good(self, building_id: int, good: int) -> None:
        from spqr.sim.models import Good

        city = self.state.player_city()
        if not (0 <= building_id < len(city.buildings)):
            return
        b = city.buildings[building_id]
        if b.kind != BuildingKind.WORKSHOP:
            return
        if b.good == good:
            return
        b.good = good
        good_name = Good(good).name.lower()
        push_log(
            self.state.log,
            self.state.tick,
            LogSeverity.INFO,
            f"Workshop at ({b.x},{b.y}) retooled for {good_name}.",
        )

    def _set_farm_crop(self, building_id: int, crop: int) -> None:
        city = self.state.player_city()
        if not (0 <= building_id < len(city.buildings)):
            return
        b = city.buildings[building_id]
        if b.kind != BuildingKind.FARM:
            return
        if b.crop == crop:
            return
        # Switching crops resets the in-progress harvest — different
        # plantings, different soil prep.
        b.crop = crop
        b.grain_maturity = 0.0
        from spqr.sim.models import Crop  # local import to avoid cycle
        crop_name = Crop(crop).name.lower()
        push_log(
            self.state.log,
            self.state.tick,
            LogSeverity.INFO,
            f"Farm at ({b.x},{b.y}) replanted with {crop_name}.",
        )

    def _place_zone_rect(
        self, x1: int, y1: int, x2: int, y2: int, kind: ZoneKind
    ) -> None:
        city = self.state.player_city()
        # Office is a multi-tile building; rectangle drag doesn't
        # apply. Force the 2×2 footprint anchored at (x1, y1) and let
        # the dedicated placer handle all-or-nothing buildability.
        if kind == ZoneKind.OFFICE:
            self._place_office_at(x1, y1)
            return
        # Destructive tools route to dedicated removal handlers — they
        # delete buildings instead of placing them, with their own
        # refund and cost rules.
        if kind == ZoneKind.UNDESIGNATE:
            self._undesignate_rect(x1, y1, x2, y2)
            return
        if kind == ZoneKind.BULLDOZE:
            self._bulldoze_rect(x1, y1, x2, y2)
            return
        b_kind = _ZONE_TO_BUILDING[kind]
        cost = BUILDING_COST[b_kind]
        x_lo, x_hi = (x1, x2) if x1 <= x2 else (x2, x1)
        y_lo, y_hi = (y1, y2) if y1 <= y2 else (y2, y1)
        district = city.districts[0] if city.districts else None
        placed = 0
        unaffordable = 0
        for y in range(y_lo, y_hi + 1):
            for x in range(x_lo, x_hi + 1):
                if not city.is_buildable(x, y):
                    continue
                if not city.treasury.can_pay(cost):
                    unaffordable += 1
                    continue
                city.treasury.pay(cost)
                # RESIDENCE designations skip construction: tier-0 plots
                # are undeveloped land that admits migrants immediately.
                # Higher tiers are earned by the housing system as
                # amenities arrive.
                completion = 1.0 if b_kind == BuildingKind.RESIDENCE else 0.0
                building = Building(
                    id=city.next_building_id,
                    kind=b_kind,
                    x=x,
                    y=y,
                    completion=completion,
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

    def _place_office_at(self, x: int, y: int) -> None:
        """Place a 2×2 office anchored at (x, y). All four tiles must
        be buildable; cost is paid once. All four tile.building_ids
        point to the same office struct so the inspector resolves to
        the same building from any corner."""
        from spqr.sim.models import OFFICE_FOOTPRINT_H, OFFICE_FOOTPRINT_W

        city = self.state.player_city()
        cost = BUILDING_COST[BuildingKind.OFFICE]
        footprint = [
            (x + dx, y + dy)
            for dy in range(OFFICE_FOOTPRINT_H)
            for dx in range(OFFICE_FOOTPRINT_W)
        ]
        # All-or-nothing buildability check.
        for tx, ty in footprint:
            if not city.is_buildable(tx, ty):
                push_log(
                    self.state.log,
                    self.state.tick,
                    LogSeverity.WARNING,
                    f"Cannot place office at ({x},{y}): footprint blocked.",
                )
                return
        if not city.treasury.can_pay(cost):
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.WARNING,
                f"Cannot afford office: need "
                f"{int(cost.denarii)}d {int(cost.timber)}t {int(cost.stone)}s.",
            )
            return
        city.treasury.pay(cost)
        building = Building(
            id=city.next_building_id,
            kind=BuildingKind.OFFICE,
            x=x,
            y=y,
            completion=0.0,
        )
        city.next_building_id += 1
        city.buildings.append(building)
        for tx, ty in footprint:
            city.tile(tx, ty).building_id = building.id
        district = city.districts[0] if city.districts else None
        if district is not None:
            district.building_ids.append(building.id)
        push_log(
            self.state.log,
            self.state.tick,
            LogSeverity.INFO,
            f"Designated office at ({x},{y}).",
        )

    # --- Destructive tools -------------------------------------------------

    def _undesignate_rect(
        self, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        """Cancel any under-construction designations inside the rect.
        Each cancelled building refunds 100% of its BUILDING_COST.
        Completed buildings are skipped — use bulldoze for those."""
        city = self.state.player_city()
        x_lo, x_hi = (x1, x2) if x1 <= x2 else (x2, x1)
        y_lo, y_hi = (y1, y2) if y1 <= y2 else (y2, y1)
        seen_ids: set[int] = set()
        removed = 0
        skipped_completed = 0
        for y in range(y_lo, y_hi + 1):
            for x in range(x_lo, x_hi + 1):
                if not city.in_bounds(x, y):
                    continue
                tile = city.tile(x, y)
                if tile.building_id == -1:
                    continue
                b = city.buildings[tile.building_id]
                if b.id in seen_ids:
                    continue
                seen_ids.add(b.id)
                if b.is_completed:
                    skipped_completed += 1
                    continue
                cost = BUILDING_COST.get(b.kind)
                if cost is not None:
                    city.treasury.denarii += cost.denarii
                    city.treasury.timber += cost.timber
                    city.treasury.stone += cost.stone
                self._tombstone_building(b)
                removed += 1
        if removed == 0 and skipped_completed == 0:
            return
        if removed > 0:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.INFO,
                f"Undesignated {removed} building(s); cost fully refunded.",
            )
        if skipped_completed > 0:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.WARNING,
                f"Skipped {skipped_completed} completed building(s) — "
                "use bulldoze (z) to demolish those.",
            )

    def _bulldoze_rect(
        self, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        """Demolish buildings inside the rect. Each removal costs
        BULLDOZE_DENARII_COST and refunds BULLDOZE_REFUND_FRACTION of
        the original timber+stone (no denarii refund — that's gone to
        operations). If the treasury can't pay the bulldoze fee, the
        rest of the rect is skipped."""
        from spqr.sim.models import (
            BULLDOZE_DENARII_COST,
            BULLDOZE_REFUND_FRACTION,
        )

        city = self.state.player_city()
        x_lo, x_hi = (x1, x2) if x1 <= x2 else (x2, x1)
        y_lo, y_hi = (y1, y2) if y1 <= y2 else (y2, y1)
        seen_ids: set[int] = set()
        removed = 0
        skipped_no_funds = 0
        for y in range(y_lo, y_hi + 1):
            for x in range(x_lo, x_hi + 1):
                if not city.in_bounds(x, y):
                    continue
                tile = city.tile(x, y)
                if tile.building_id == -1:
                    continue
                b = city.buildings[tile.building_id]
                if b.id in seen_ids:
                    continue
                seen_ids.add(b.id)
                if city.treasury.denarii < BULLDOZE_DENARII_COST:
                    skipped_no_funds += 1
                    continue
                city.treasury.denarii -= BULLDOZE_DENARII_COST
                cost = BUILDING_COST.get(b.kind)
                if cost is not None:
                    city.treasury.timber += cost.timber * BULLDOZE_REFUND_FRACTION
                    city.treasury.stone += cost.stone * BULLDOZE_REFUND_FRACTION
                self._tombstone_building(b)
                removed += 1
        if removed == 0 and skipped_no_funds == 0:
            return
        if removed > 0:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.INFO,
                f"Bulldozed {removed} building(s).",
            )
        if skipped_no_funds > 0:
            push_log(
                self.state.log,
                self.state.tick,
                LogSeverity.WARNING,
                f"Could not afford to bulldoze {skipped_no_funds} more — "
                f"need {int(BULLDOZE_DENARII_COST)}d each.",
            )

    def _tombstone_building(self, b: Building) -> None:
        """Remove a building from the city: clear its footprint tiles,
        drop it from the owning district, and mark the slot EMPTY.
        The buildings list keeps the entry as a tombstone (kind=EMPTY)
        rather than reindexing, so existing tile.building_id values
        remain stable. All consumer iterators skip EMPTY kinds."""
        city = self.state.player_city()
        for fx, fy in _building_footprint(b):
            if city.in_bounds(fx, fy):
                city.tile(fx, fy).building_id = -1
        for d in city.districts:
            if b.id in d.building_ids:
                d.building_ids.remove(b.id)
        b.kind = BuildingKind.EMPTY
        b.workers_assigned = 0


def _building_footprint(b: Building) -> list[tuple[int, int]]:
    """Tiles a building occupies. OFFICE is 2×2 anchored at (b.x, b.y);
    every other kind is a single tile. Used by removal helpers so the
    full footprint is cleared in one pass."""
    if b.kind == BuildingKind.OFFICE:
        from spqr.sim.models import OFFICE_FOOTPRINT_H, OFFICE_FOOTPRINT_W

        return [
            (b.x + dx, b.y + dy)
            for dy in range(OFFICE_FOOTPRINT_H)
            for dx in range(OFFICE_FOOTPRINT_W)
        ]
    return [(b.x, b.y)]
