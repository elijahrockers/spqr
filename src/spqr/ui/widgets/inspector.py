"""Inspector panel — shows what's under the city-map cursor.

For an empty tile, displays terrain type and buildability hint. For a
building, displays kind, completion, builders or workers, district,
storage capacity (if any), and farm output."""

from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from spqr.engine.world import GameState
from spqr.sim.models import (
    BUILDER_SLOTS,
    GRAIN_PER_MEAL,
    GRANARY_CAPACITY,
    GROWING_SEASON_MONTHS,
    LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK,
    QUARRY_STONE_PER_WORKER_PER_TICK,
    RESIDENCE_MAX_TIER,
    RESIDENCE_TIER_NAME,
    MEAL_INTERVAL_HOURS,
    STORAGE_CAPACITY,
    WAREHOUSE_VEGETABLES_CAPACITY,
    BuildingKind,
    City,
    Crop,
    hours_until_next_meal,
)


class Inspector(Widget):
    DEFAULT_CSS = """
    Inspector {
        border: solid $accent;
        height: 16;
        padding: 0 1;
    }
    """

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.border_title = "Tile inspector"
        self.cursor_x = 0
        self.cursor_y = 0

    def set_cursor(self, x: int, y: int) -> None:
        if (x, y) == (self.cursor_x, self.cursor_y):
            return
        self.cursor_x = x
        self.cursor_y = y
        self.refresh()

    def render(self) -> Text:
        city = self.state.player_city()
        x, y = self.cursor_x, self.cursor_y
        if not city.in_bounds(x, y):
            return Text("(out of bounds)")
        tile = city.tile(x, y)
        if tile.building_id == -1:
            return _render_terrain(city, x, y)
        _, month, _ = self.state.date()
        return _render_building(city, x, y, month, self.state.tick)


def _render_terrain(city: City, x: int, y: int) -> Text:
    tile = city.tile(x, y)
    text = Text()
    text.append(f"({x},{y})  ", style="grey50")
    text.append(tile.terrain.name.title(), style="bold green")
    text.append("\n\n")
    text.append("Empty tile.\n", style="grey70")
    if city.is_buildable(x, y):
        text.append("Buildable", style="green")
    else:
        text.append("Not buildable", style="red")
        text.append(" (water/rock/forest/hill)", style="grey50")
    return text


def _render_building(city: City, x: int, y: int, current_month: int, current_tick: int) -> Text:
    tile = city.tile(x, y)
    b = city.buildings[tile.building_id]
    text = Text()
    text.append(f"({x},{y})  ", style="grey50")
    text.append(b.kind.name.title(), style="bold bright_white")
    if b.is_under_construction:
        text.append("  [under construction]", style="yellow")
    text.append("\n\n")

    if b.is_under_construction:
        # Mid-construction view: builders + progress.
        pct = int(b.completion * 100)
        builder_slots = BUILDER_SLOTS.get(b.kind, 1)
        text.append("Completion: ", style="grey70")
        text.append(f"{pct}%\n", style="yellow")
        text.append("Builders:   ", style="grey70")
        builder_color = "cyan" if b.workers_assigned > 0 else "red"
        text.append(f"{b.workers_assigned}/{builder_slots}", style=builder_color)
        if b.workers_assigned == 0:
            text.append("  (stalled — no labor)", style="red")
        text.append("\n")
    else:
        # Operational view.
        slots = b.operational_worker_slots()
        if slots > 0:
            text.append("Workers:    ", style="grey70")
            text.append(f"{b.workers_assigned}/{slots}\n", style="cyan")
        cap = b.residence_capacity()
        if cap > 0 or b.kind == BuildingKind.RESIDENCE:
            occupancy = _residence_occupancy(city, b)
            full = cap > 0 and occupancy >= cap
            color = "bright_green" if full else "cyan"
            text.append("Housing:    ", style="grey70")
            if b.kind == BuildingKind.RESIDENCE:
                tier_name = RESIDENCE_TIER_NAME.get(b.tier, "?")
                text.append(f"{occupancy}/{cap} plebs", style=color)
                text.append(
                    f"  ({tier_name}, tier {b.tier}/{RESIDENCE_MAX_TIER})\n",
                    style="grey50",
                )
            else:
                text.append(f"{occupancy}/{cap} patricians\n", style=color)
        storage = STORAGE_CAPACITY.get(b.kind, 0)
        if storage > 0:
            text.append("Storage:    ", style="grey70")
            text.append(f"{storage} units\n", style="bright_cyan")
            stored = city.stored_materials()
            total_cap = city.total_storage_capacity()
            text.append("City stocks:\n", style="grey70")
            text.append(f"  timber {city.treasury.timber:.0f}", style="white")
            text.append(f"  stone {city.treasury.stone:.0f}", style="white")
            text.append(f"   ({stored:.0f} / {total_cap})\n", style="grey50")
        if b.kind == BuildingKind.FARM:
            _render_farm_grain(text, b, current_month)
        if b.kind == BuildingKind.GRANARY:
            _render_granary_grain(text, b)
        if b.kind == BuildingKind.WAREHOUSE:
            _render_warehouse_veg(text, b)
        if b.kind in (BuildingKind.LUMBER_MILL, BuildingKind.QUARRY):
            _render_industry(text, city, b)
        if b.kind in (BuildingKind.RESIDENCE, BuildingKind.DOMUS):
            _render_residence_meals(text, city, b, current_tick)

    district = _district_for_building(city, b.id)
    if district is not None:
        text.append("District:   ", style="grey70")
        text.append(f"{district}\n", style="bright_white")
    return text


def _render_farm_grain(text: Text, b, month: int) -> None:  # type: ignore[no-untyped-def]
    in_season = month in GROWING_SEASON_MONTHS
    crop_name = Crop(b.crop).name.lower()
    text.append("Sown with:  ", style="grey70")
    text.append(f"{crop_name}\n", style="bright_yellow")
    pct = int(b.grain_maturity * 100)
    text.append("Maturity:   ", style="grey70")
    bar_len = 12
    filled = int(b.grain_maturity * bar_len)
    text.append("[" + "#" * filled + "·" * (bar_len - filled) + "]", style="green")
    text.append(f" {pct}%\n", style="yellow")
    text.append("Season:     ", style="grey70")
    if in_season:
        text.append("growing\n", style="green")
    else:
        text.append("dormant\n", style="grey50")
    in_transit = (
        b.grain_stored if b.crop == int(Crop.WHEAT) else b.vegetables_stored
    )
    if in_transit > 0:
        text.append("Awaiting:   ", style="grey70")
        text.append(f"{in_transit:.0f} {crop_name} ", style="bright_yellow")
        text.append("(in transit)\n", style="grey50")
    text.append("Yield:      ", style="grey70")
    text.append(
        f"~{int(b.farm_yield_per_harvest())} per harvest\n", style="grey70"
    )


def _render_granary_grain(text: Text, b) -> None:  # type: ignore[no-untyped-def]
    text.append("Grain:      ", style="grey70")
    pct = b.grain_stored / max(GRANARY_CAPACITY, 1.0)
    color = "green" if pct >= 0.5 else "yellow" if pct >= 0.2 else "red"
    text.append(
        f"{b.grain_stored:.0f} / {int(GRANARY_CAPACITY)}\n", style=color
    )


def _render_industry(text: Text, city: City, b) -> None:  # type: ignore[no-untyped-def]
    is_mill = b.kind == BuildingKind.LUMBER_MILL
    rate = (
        LUMBER_MILL_TIMBER_PER_WORKER_PER_TICK if is_mill
        else QUARRY_STONE_PER_WORKER_PER_TICK
    )
    output = "timber" if is_mill else "stone"
    per_tick = rate * b.workers_assigned
    text.append("Output:     ", style="grey70")
    text.append(f"{per_tick:.2f} {output}/hr", style="bright_yellow")
    text.append(f"  ({rate:.2f}×{b.workers_assigned})\n", style="grey50")
    stored = city.stored_materials()
    cap = city.total_storage_capacity()
    text.append("Storage:    ", style="grey70")
    over_cap = stored >= cap
    color = "red" if over_cap else "white"
    text.append(f"{stored:.0f} / {cap}", style=color)
    if over_cap:
        text.append("  (production halted)", style="red")
    text.append("\n")


def _render_warehouse_veg(text: Text, b) -> None:  # type: ignore[no-untyped-def]
    text.append("Vegetables: ", style="grey70")
    pct = b.vegetables_stored / max(WAREHOUSE_VEGETABLES_CAPACITY, 1.0)
    color = "green" if pct >= 0.5 else "yellow" if pct >= 0.2 else "red"
    text.append(
        f"{b.vegetables_stored:.0f} / {int(WAREHOUSE_VEGETABLES_CAPACITY)}\n",
        style=color,
    )


def _render_residence_meals(text: Text, city: City, b, current_tick: int) -> None:  # type: ignore[no-untyped-def]
    """Lean residence summary. Per-source granary/warehouse stocks
    moved to the (i)nfo panel; here we just show the high-level food
    access count and the next meal time."""
    from spqr.sim.systems.spatial import coverage
    from spqr.sim.models import GRANARY_REACH_COST

    grain_in_reach = 0.0
    veg_in_reach = 0.0
    for s in city.completed_of(BuildingKind.GRANARY):
        cov = coverage(city, s.x, s.y, GRANARY_REACH_COST)
        if (b.x, b.y) in cov:
            grain_in_reach += s.grain_stored
    for s in city.completed_of(BuildingKind.WAREHOUSE):
        cov = coverage(city, s.x, s.y, GRANARY_REACH_COST)
        if (b.x, b.y) in cov:
            veg_in_reach += s.vegetables_stored
    food_types = (1 if grain_in_reach > 0 else 0) + (1 if veg_in_reach > 0 else 0)
    text.append("Food types: ", style="grey70")
    color = "bright_green" if food_types >= 2 else "yellow" if food_types == 1 else "red"
    text.append(f"{food_types}", style=color)
    if food_types >= 2:
        text.append("  (variety bonus active)", style="grey50")
    elif food_types == 0:
        text.append("  (residents starve)", style="grey50")
    text.append("\n")
    if b.kind == BuildingKind.RESIDENCE:
        _render_meal_line(text, "Pleb", 0, current_tick)
    elif b.kind == BuildingKind.DOMUS:
        _render_meal_line(text, "Pat", 1, current_tick)


def _render_meal_line(text: Text, label: str, cls: int, current_tick: int) -> None:
    interval = MEAL_INTERVAL_HOURS[cls]
    per_meal = GRAIN_PER_MEAL[cls]
    until = hours_until_next_meal(current_tick, cls)
    text.append(f"{label} meal:  ", style="grey70")
    if until == 0:
        text.append("now", style="bright_yellow")
    else:
        text.append(f"in {until:>2}h", style="cyan")
    text.append(
        f"  ({per_meal:.2f}g, every {interval}h)\n", style="grey50"
    )


def _district_for_building(city: City, b_id: int) -> str | None:
    for d in city.districts:
        if b_id in d.building_ids:
            return d.name
    return None


def _residence_occupancy(city: City, b) -> int:  # type: ignore[no-untyped-def]
    """Integer share of district pops housed in this building.

    Pops are tracked at the district level, so per-residence occupancy
    is a derived display. We allocate the rounded district pop using
    Hamilton's largest-remainder method weighted by capacity, so the
    per-residence integers sum to exactly the same number the status
    bar shows for the district. Without this, three residences each
    formatted as `f"{pops*cap/total_cap:.0f}"` independently round
    upward and the inspector reports more pops than the city has."""
    cap = b.residence_capacity()
    if cap <= 0:
        return 0
    if b.kind == BuildingKind.RESIDENCE:
        match_kind = BuildingKind.RESIDENCE
    elif b.kind == BuildingKind.DOMUS:
        match_kind = BuildingKind.DOMUS
    else:
        return 0
    for d in city.districts:
        if b.id not in d.building_ids:
            continue
        residences = sorted(
            (
                city.buildings[b_id]
                for b_id in d.building_ids
                if city.buildings[b_id].kind == match_kind
                and city.buildings[b_id].is_completed
            ),
            key=lambda r: r.id,
        )
        if not residences:
            return 0
        total_cap = sum(r.residence_capacity() for r in residences)
        if total_cap <= 0:
            return 0
        pops = (
            d.pops.plebs if match_kind == BuildingKind.RESIDENCE
            else d.pops.patricians
        )
        # Match the status bar's `:5.0f` rounding so totals tie out.
        total_int = round(pops)
        # Floor allocation by proportional share, then hand out the
        # leftover one-by-one to residences with the largest fractional
        # remainders (Hamilton's method). Stable id ordering for ties.
        floors: list[int] = []
        fracs: list[float] = []
        for r in residences:
            exact = total_int * r.residence_capacity() / total_cap
            f = int(exact)
            floors.append(f)
            fracs.append(exact - f)
        leftover = total_int - sum(floors)
        # Indices ranked by fractional descending, then id ascending.
        order = sorted(
            range(len(residences)),
            key=lambda i: (-fracs[i], residences[i].id),
        )
        for idx in order[:max(0, leftover)]:
            floors[idx] += 1
        for r, occupancy in zip(residences, floors):
            if r.id == b.id:
                return min(cap, occupancy)
        return 0
    return 0
