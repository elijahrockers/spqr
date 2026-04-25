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
    GRAIN_PER_LEGIONARY_MEAL,
    GRAIN_PER_MEAL,
    GRAIN_YIELD_PER_HARVEST,
    GRANARY_CAPACITY,
    GROWING_SEASON_MONTHS,
    HOUSING_CAPACITY,
    LEGIONARY_MEAL_INTERVAL_HOURS,
    MEAL_INTERVAL_HOURS,
    STORAGE_CAPACITY,
    WORKER_SLOTS,
    BuildingKind,
    City,
    hours_until_legionary_meal,
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
    from spqr.engine.tick import is_buildable

    tile = city.tile(x, y)
    text = Text()
    text.append(f"({x},{y})  ", style="grey50")
    text.append(tile.terrain.name.title(), style="bold green")
    text.append("\n\n")
    text.append("Empty tile.\n", style="grey70")
    if is_buildable(city, x, y):
        text.append("Buildable", style="green")
    else:
        text.append("Not buildable", style="red")
        text.append(" (water/rock/forest/hill)", style="grey50")
    return text


def _render_building(city: City, x: int, y: int, current_month: int, current_tick: int) -> Text:
    from spqr.engine.tick import stored_materials, total_storage_capacity

    tile = city.tile(x, y)
    b = city.buildings[tile.building_id]
    text = Text()
    text.append(f"({x},{y})  ", style="grey50")
    text.append(b.kind.name.title(), style="bold bright_white")
    if b.completion < 1.0:
        text.append("  [under construction]", style="yellow")
    text.append("\n\n")

    if b.completion < 1.0:
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
        slots = WORKER_SLOTS.get(b.kind, 0)
        if slots > 0:
            text.append("Workers:    ", style="grey70")
            text.append(f"{b.workers_assigned}/{slots}\n", style="cyan")
        cap = HOUSING_CAPACITY.get(b.kind, 0)
        if cap > 0:
            text.append("Housing:    ", style="grey70")
            text.append(f"{cap}\n", style="cyan")
        storage = STORAGE_CAPACITY.get(b.kind, 0)
        if storage > 0:
            text.append("Storage:    ", style="grey70")
            text.append(f"{storage} units\n", style="bright_cyan")
            stored = stored_materials(city)
            total_cap = total_storage_capacity(city)
            text.append("City stocks:\n", style="grey70")
            text.append(f"  timber {city.treasury.timber:.0f}", style="white")
            text.append(f"  stone {city.treasury.stone:.0f}", style="white")
            text.append(f"   ({stored:.0f} / {total_cap})\n", style="grey50")
        if b.kind == BuildingKind.FARM:
            _render_farm_grain(text, b, current_month)
        if b.kind == BuildingKind.GRANARY:
            _render_granary_grain(text, b)
        if b.kind in (BuildingKind.INSULA, BuildingKind.DOMUS):
            _render_house_meals(text, city, b, current_tick)
        if b.kind == BuildingKind.BARRACKS:
            _render_barracks_meals(text, city, b, current_tick)

    district = _district_for_building(city, b.id)
    if district is not None:
        text.append("District:   ", style="grey70")
        text.append(f"{district}\n", style="bright_white")
    return text


def _render_farm_grain(text: Text, b, month: int) -> None:  # type: ignore[no-untyped-def]
    in_season = month in GROWING_SEASON_MONTHS
    pct = int(b.grain_maturity * 100)
    text.append("Crop:       ", style="grey70")
    bar_len = 12
    filled = int(b.grain_maturity * bar_len)
    text.append("[" + "#" * filled + "·" * (bar_len - filled) + "]", style="green")
    text.append(f" {pct}%\n", style="yellow")
    text.append("Season:     ", style="grey70")
    if in_season:
        text.append("growing\n", style="green")
    else:
        text.append("dormant\n", style="grey50")
    if b.grain_stored > 0:
        text.append("Awaiting:   ", style="grey70")
        text.append(f"{b.grain_stored:.0f} grain ", style="bright_yellow")
        text.append("(in transit)\n", style="grey50")
    text.append("Yield:      ", style="grey70")
    text.append(
        f"~{int(GRAIN_YIELD_PER_HARVEST)} per harvest\n", style="grey70"
    )


def _render_granary_grain(text: Text, b) -> None:  # type: ignore[no-untyped-def]
    text.append("Grain:      ", style="grey70")
    pct = b.grain_stored / max(GRANARY_CAPACITY, 1.0)
    color = "green" if pct >= 0.5 else "yellow" if pct >= 0.2 else "red"
    text.append(
        f"{b.grain_stored:.0f} / {int(GRANARY_CAPACITY)}\n", style=color
    )


def _render_house_meals(text: Text, city: City, b, current_tick: int) -> None:  # type: ignore[no-untyped-def]
    # Compute granaries whose coverage includes this house's tile.
    from spqr.sim.systems.spatial import coverage
    from spqr.sim.models import GRANARY_REACH_COST

    in_range_count = 0
    in_range_grain = 0.0
    for g in city.buildings:
        if g.kind != BuildingKind.GRANARY or g.completion < 1.0:
            continue
        cov = coverage(city, g.x, g.y, GRANARY_REACH_COST)
        if (b.x, b.y) in cov:
            in_range_count += 1
            in_range_grain += g.grain_stored
    text.append("Granaries:  ", style="grey70")
    if in_range_count > 0:
        text.append(f"{in_range_count} in range", style="green")
        text.append(f" ({in_range_grain:.0f} grain)\n", style="grey50")
    else:
        text.append("none in range", style="red")
        text.append(" (residents starve)\n", style="grey50")
    # Two resident classes per house kind. Show each meal schedule.
    if b.kind == BuildingKind.INSULA:
        text.append("Residents:  ", style="grey70")
        text.append(f"plebs + slaves (×{HOUSING_CAPACITY[b.kind]})\n", style="white")
        _render_meal_line(text, "Pleb",  1, current_tick)
        _render_meal_line(text, "Slave", 0, current_tick)
    elif b.kind == BuildingKind.DOMUS:
        text.append("Residents:  ", style="grey70")
        text.append(
            f"equites + patricians (×{HOUSING_CAPACITY[b.kind]})\n", style="white"
        )
        _render_meal_line(text, "Equ",   2, current_tick)
        _render_meal_line(text, "Pat",   3, current_tick)


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


def _render_barracks_meals(text: Text, city: City, b, current_tick: int) -> None:  # type: ignore[no-untyped-def]
    from spqr.sim.systems.spatial import coverage
    from spqr.sim.models import GRANARY_REACH_COST

    in_range_count = 0
    in_range_grain = 0.0
    for g in city.buildings:
        if g.kind != BuildingKind.GRANARY or g.completion < 1.0:
            continue
        cov = coverage(city, g.x, g.y, GRANARY_REACH_COST)
        if (b.x, b.y) in cov:
            in_range_count += 1
            in_range_grain += g.grain_stored
    text.append("Granaries:  ", style="grey70")
    if in_range_count > 0:
        text.append(f"{in_range_count} in range", style="green")
        text.append(f" ({in_range_grain:.0f} grain)\n", style="grey50")
    else:
        text.append("none in range", style="red")
        text.append(" (soldiers starve)\n", style="grey50")
    text.append("Garrison:   ", style="grey70")
    text.append(f"{city.garrison.legionaries} legionaries\n", style="red")
    until = hours_until_legionary_meal(current_tick)
    text.append("Mess:       ", style="grey70")
    if until == 0:
        text.append("now", style="bright_yellow")
    else:
        text.append(f"in {until:>2}h", style="cyan")
    text.append(
        f"  ({GRAIN_PER_LEGIONARY_MEAL:.2f}g, every {LEGIONARY_MEAL_INTERVAL_HOURS}h)\n",
        style="grey50",
    )


def _district_for_building(city: City, b_id: int) -> str | None:
    for d in city.districts:
        if b_id in d.building_ids:
            return d.name
    return None
