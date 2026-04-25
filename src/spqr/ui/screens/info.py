"""Advanced (i)nfo modal — extended detail for the building under the
cursor. For granaries, exposes (r)ange highlight and (g)raph hotkeys.

Other building kinds show plain extended info; future milestones can add
kind-specific actions in the same dispatch shape."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget

from spqr.engine.world import GameState
from spqr.sim.models import (
    BuildingKind,
    City,
    GRANARY_CAPACITY,
    GRANARY_HISTORY_MAX_SAMPLES,
    GRANARY_REACH_COST,
)


@dataclass(slots=True)
class InfoResult:
    """What InfoScreen sends back to the App.

    `kind` is one of:
      "close"     — modal dismissed; no further action
      "highlight" — App should show this granary's coverage on the city map
      "graph"     — App should open the inventory-history graph screen
    """
    kind: str
    granary_id: int | None = None


# --- Info screen ------------------------------------------------------------


class _InfoBody(Widget):
    DEFAULT_CSS = """
    _InfoBody { height: auto; }
    """

    def __init__(self, state: GameState, building_id: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.building_id = building_id

    def render(self) -> Text:
        city = self.state.player_city()
        b = city.buildings[self.building_id]
        if b.kind == BuildingKind.GRANARY:
            return _render_granary_info(self.state, city, b)
        return _render_generic_info(b)


class InfoScreen(ModalScreen[InfoResult]):
    DEFAULT_CSS = """
    InfoScreen {
        align: center middle;
    }
    InfoScreen > Vertical {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("i", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("r", "highlight", "Highlight range", show=False),
        Binding("g", "graph", "Graph", show=False),
    ]

    def __init__(self, state: GameState, building_id: int) -> None:
        super().__init__()
        self.state = state
        self.building_id = building_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield _InfoBody(self.state, self.building_id)

    def on_mount(self) -> None:
        # Refresh while open so live numbers stay current.
        self.set_interval(0.5, lambda: self.query_one(_InfoBody).refresh())

    def _is_granary(self) -> bool:
        b = self.state.player_city().buildings[self.building_id]
        return b.kind == BuildingKind.GRANARY

    def action_close(self) -> None:
        self.dismiss(InfoResult(kind="close"))

    def action_highlight(self) -> None:
        if not self._is_granary():
            return
        self.dismiss(InfoResult(kind="highlight", granary_id=self.building_id))

    def action_graph(self) -> None:
        if not self._is_granary():
            return
        self.dismiss(InfoResult(kind="graph", granary_id=self.building_id))


def _render_generic_info(b) -> Text:  # type: ignore[no-untyped-def]
    text = Text()
    text.append("INFO\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")
    text.append(f"  {b.kind.name.title()}", style="bold bright_white")
    text.append(f"   ({b.x}, {b.y})\n\n", style="grey50")
    text.append(f"  Completion:  {int(b.completion * 100)}%\n", style="grey70")
    text.append(f"  Workers:     {b.workers_assigned}\n", style="grey70")
    text.append("\n[dim]escape / i to close[/]\n")
    return text


def _render_granary_info(state: GameState, city: City, b) -> Text:  # type: ignore[no-untyped-def]
    from spqr.sim.systems.spatial import coverage

    text = Text()
    text.append("GRANARY INFO\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")

    text.append(f"  Position:    ({b.x}, {b.y})\n", style="grey70")
    pct = b.grain_stored / max(GRANARY_CAPACITY, 1.0)
    color = "green" if pct >= 0.5 else "yellow" if pct >= 0.2 else "red"
    text.append("  Stored:      ", style="grey70")
    text.append(
        f"{b.grain_stored:.0f} / {int(GRANARY_CAPACITY)} ({pct*100:.0f}%)\n",
        style=color,
    )

    cov = coverage(city, b.x, b.y, GRANARY_REACH_COST)
    served = [
        ob for ob in city.buildings
        if ob.completion >= 1.0
        and (ob.x, ob.y) in cov
        and ob.id != b.id
    ]
    insulae = sum(1 for ob in served if ob.kind == BuildingKind.INSULA)
    domus = sum(1 for ob in served if ob.kind == BuildingKind.DOMUS)
    barracks = sum(1 for ob in served if ob.kind == BuildingKind.BARRACKS)
    farms = sum(1 for ob in served if ob.kind == BuildingKind.FARM)
    text.append(f"  Reach:       {len(cov)} tiles\n", style="grey70")
    text.append(f"  Serves:      ", style="grey70")
    text.append(
        f"{insulae} insulae · {domus} domus · {barracks} barracks · {farms} farms\n",
        style="white",
    )

    history_len = len(b.inventory_history)
    days = history_len // 24
    text.append(
        f"  History:     {history_len} hourly samples ({days}d {history_len%24}h)\n",
        style="grey70",
    )
    text.append("\n")

    text.append("  [bright_yellow]R[/]  Highlight range on city map\n")
    text.append("  [bright_yellow]G[/]  Inventory graph\n\n")
    text.append("[dim]escape / i to close[/]\n")
    return text


# --- Graph screen -----------------------------------------------------------


class _GraphBody(Widget):
    DEFAULT_CSS = """
    _GraphBody { height: auto; }
    """

    def __init__(self, state: GameState, building_id: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.building_id = building_id
        self.daily = False

    def render(self) -> Text:
        city = self.state.player_city()
        b = city.buildings[self.building_id]
        return _render_graph(b, self.daily)


class GraphScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    GraphScreen {
        align: center middle;
    }
    GraphScreen > Vertical {
        width: 80;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("g", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("d", "toggle_resolution", "Daily/hourly"),
    ]

    def __init__(self, state: GameState, building_id: int) -> None:
        super().__init__()
        self.state = state
        self.building_id = building_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield _GraphBody(self.state, self.building_id)

    def on_mount(self) -> None:
        self.set_interval(0.5, lambda: self.query_one(_GraphBody).refresh())

    def action_close(self) -> None:
        self.dismiss(None)

    def action_toggle_resolution(self) -> None:
        body = self.query_one(_GraphBody)
        body.daily = not body.daily
        body.refresh()


# Quantization characters for sparkline-style bars.
_BLOCKS = " ▁▂▃▄▅▆▇█"


def _render_graph(b, daily: bool) -> Text:  # type: ignore[no-untyped-def]
    text = Text()
    text.append("GRANARY INVENTORY", style="bold")
    text.append(f"  ({b.x}, {b.y})\n", style="grey50")
    text.append("─" * 60 + "\n\n", style="grey50")

    samples = list(b.inventory_history)
    if not samples:
        text.append("  (no history yet — let the sim run)\n", style="grey70")
        text.append("\n[dim]d to toggle daily/hourly  ·  esc to close[/]\n")
        return text

    if daily:
        # Group by 24-hour windows; report the average per day.
        groups = []
        for i in range(0, len(samples), 24):
            chunk = samples[i:i + 24]
            groups.append(sum(chunk) / len(chunk))
        values = groups
        x_label = f"{len(values)} days"
        resolution_label = "daily (avg)"
    else:
        # Most recent ~60 hours fits comfortably; use up to 60.
        values = samples[-60:]
        x_label = f"last {len(values)} hours"
        resolution_label = "hourly"

    cap = GRANARY_CAPACITY
    cur = samples[-1]
    mn = min(values)
    mx = max(values)

    text.append(
        f"  Resolution: ", style="grey70"
    )
    text.append(f"{resolution_label}\n", style="bright_white")
    text.append(
        f"  Window:     {x_label}\n", style="grey70"
    )
    text.append(
        f"  Now: ", style="grey70"
    )
    pct = cur / max(cap, 1.0)
    cur_color = "green" if pct >= 0.5 else "yellow" if pct >= 0.2 else "red"
    text.append(f"{cur:.0f}", style=cur_color)
    text.append(f"  Min: {mn:.0f}  Max: {mx:.0f}", style="grey70")
    text.append(f"  Cap: {int(cap)}\n\n", style="grey70")

    # Bars: scale each value to [0, 8] using cap as ceiling so the chart
    # always reflects "fraction of capacity," not relative min/max.
    bars: list[str] = []
    for v in values:
        ratio = max(0.0, min(1.0, v / cap)) if cap > 0 else 0.0
        idx = int(ratio * 8 + 0.5)
        idx = max(0, min(8, idx))
        bars.append(_BLOCKS[idx])
    text.append("  ")
    text.append("".join(bars), style="green")
    text.append("\n")
    text.append(
        "  " + ("─" * len(values)) + "\n", style="grey50"
    )
    text.append(
        f"  {'older':<{max(1, len(values) // 2)}}{'now':>{max(1, (len(values) + 1) // 2)}}\n",
        style="grey50",
    )

    text.append("\n[dim]d to toggle daily/hourly  ·  esc to close[/]\n")
    return text
