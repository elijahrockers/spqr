"""Population overview screen.

Modal that summarizes the player city's populace: class breakdown, labor
utilization, housing capacity vs. homeless, and per-district mood. Reads
live state each render and self-refreshes at ~5 Hz so the player can
watch numbers move while the engine ticks underneath."""

from __future__ import annotations

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
    residence_capacity,
    WORKER_SLOTS,
)


REFRESH_HZ = 5


class _PopulationBody(Widget):
    """Renders the report body. Lives inside the modal so its render method
    is the single source of truth for the layout."""

    DEFAULT_CSS = """
    _PopulationBody {
        height: auto;
    }
    """

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state

    def render(self) -> Text:
        return _render_report(self.state)


class PopulationScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    PopulationScreen {
        align: center middle;
    }
    PopulationScreen > Vertical {
        width: 64;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("p", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def __init__(self, state: GameState) -> None:
        super().__init__()
        self.state = state
        self._body: _PopulationBody | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            self._body = _PopulationBody(self.state)
            yield self._body

    def on_mount(self) -> None:
        self.set_interval(1.0 / REFRESH_HZ, self._tick)

    def _tick(self) -> None:
        if self._body is not None:
            self._body.refresh()

    def action_close(self) -> None:
        self.dismiss(None)


def _render_report(state: GameState) -> Text:
    city = state.player_city()
    text = Text()
    text.append("POPULATION OF ", style="bold")
    text.append(city.name.upper() + "\n", style="bold bright_yellow")
    text.append("─" * 40 + "\n\n", style="grey50")

    # Composition
    text.append("Composition\n", style="bold")
    pat = sum(d.pops.patricians for d in city.districts)
    pl = sum(d.pops.plebs for d in city.districts)
    total = pat + pl
    _row(text, "Patricians", f"{pat:6.0f}", "white")
    _row(text, "Plebs",      f"{pl:6.0f}", "white")
    text.append(" " * 12 + "─" * 8 + "\n", style="grey50")
    _row(text, "Total",      f"{total:6.0f}", "bright_yellow")
    text.append("\n")

    # Labor
    text.append("Labor\n", style="bold")
    workforce = sum(d.pops.workers() for d in city.districts)
    slots = 0
    assigned = 0
    for b in city.buildings:
        if b.completion < 1.0:
            continue
        slots += WORKER_SLOTS.get(b.kind, 0)
        assigned += b.workers_assigned
    idle = max(0.0, workforce - assigned)
    _row(text, "Workforce",   f"{workforce:6.0f}", "cyan",
         "  (plebs)")
    _row(text, "Worker slots", f"{slots:6d}",      "white")
    _row(text, "Assigned",     f"{assigned:6d}",    "green")
    _row(text, "Idle",         f"{idle:6.0f}",      "yellow")
    text.append("\n")

    # Housing
    text.append("Housing\n", style="bold")
    civilian = total
    cap = 0
    for b in city.buildings:
        if b.completion < 1.0:
            continue
        if b.kind in (BuildingKind.RESIDENCE, BuildingKind.DOMUS):
            cap += residence_capacity(b)
    homeless = max(0.0, civilian - cap)
    _row(text, "Civilians",  f"{civilian:6.0f}", "white")
    _row(text, "Capacity",   f"{cap:6d}",        "white",
         "  (houses + domus)")
    _row(text, "Homeless",   f"{homeless:6.0f}",
         "red" if homeless > 0 else "green")
    text.append("\n")

    # Mood
    text.append("Districts\n", style="bold")
    for d in city.districts:
        sat = d.satisfaction
        un = d.pops.unrest
        sat_color = "green" if sat >= 0.6 else "yellow" if sat >= 0.3 else "red"
        un_color = "green" if un < 0.3 else "yellow" if un < 0.7 else "red"
        text.append(f"  {d.name:<14}", style="white")
        text.append("sat ", style="grey50")
        text.append(f"{sat:.2f}", style=sat_color)
        text.append("   unrest ", style="grey50")
        text.append(f"{un:.2f}\n", style=un_color)

    text.append("\nescape / p to close\n", style="dim")
    return text


def _row(text: Text, label: str, value: str, value_style: str, extra: str = "") -> None:
    text.append(f"  {label:<12}", style="grey70")
    text.append(value, style=value_style)
    if extra:
        text.append(extra, style="grey50")
    text.append("\n")
