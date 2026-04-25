from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from spqr.engine.commands import ZoneKind
from spqr.sim.models import BUILDING_COST, BuildingKind


_ZONE_TO_BUILDING: dict[ZoneKind, BuildingKind] = {
    ZoneKind.FARM: BuildingKind.FARM,
    ZoneKind.INSULA: BuildingKind.INSULA,
    ZoneKind.BARRACKS: BuildingKind.BARRACKS,
    ZoneKind.GRANARY: BuildingKind.GRANARY,
    ZoneKind.WORKSHOP: BuildingKind.WORKSHOP,
    ZoneKind.ROAD: BuildingKind.ROAD,
    ZoneKind.WAREHOUSE: BuildingKind.WAREHOUSE,
}


def _cost_string(zone: ZoneKind) -> str:
    cost = BUILDING_COST[_ZONE_TO_BUILDING[zone]]
    parts = []
    if cost.denarii:
        parts.append(f"{int(cost.denarii)}d")
    if cost.timber:
        parts.append(f"{int(cost.timber)}t")
    if cost.stone:
        parts.append(f"{int(cost.stone)}s")
    return " ".join(parts) if parts else "free"


# Display order: hotkey, ZoneKind to dismiss with, label. `None` means
# "clear the current tool". Cost is appended at compose time.
_OPTIONS: list[tuple[str, ZoneKind | None, str]] = [
    ("1", ZoneKind.FARM,      "Farm       — produces grain (6 workers)"),
    ("2", ZoneKind.INSULA,    "Insula     — housing for 40 plebs"),
    ("3", ZoneKind.BARRACKS,  "Barracks   — soldiers, +50 storage"),
    ("4", ZoneKind.GRANARY,   "Granary    — grain storage (2 workers)"),
    ("5", ZoneKind.WORKSHOP,  "Workshop   — 4 workers, future goods"),
    ("6", ZoneKind.ROAD,      "Road       — connects tiles"),
    ("7", ZoneKind.WAREHOUSE, "Warehouse  — +250 materials storage"),
    ("0", None,               "Clear current tool"),
]


class BuildMenuScreen(ModalScreen[ZoneKind | None]):
    """Pick a brush. The screen is initialized with the *current* tool so
    cancel paths (escape / b / q) dismiss with that value unchanged. The
    caller treats every dismiss value as "the new tool", whether or not it
    actually changed."""

    DEFAULT_CSS = """
    BuildMenuScreen {
        align: center middle;
    }
    BuildMenuScreen > Vertical {
        width: 72;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("b", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
        Binding("1", "pick('1')", show=False),
        Binding("2", "pick('2')", show=False),
        Binding("3", "pick('3')", show=False),
        Binding("4", "pick('4')", show=False),
        Binding("5", "pick('5')", show=False),
        Binding("6", "pick('6')", show=False),
        Binding("7", "pick('7')", show=False),
        Binding("0", "pick('0')", show=False),
    ]

    def __init__(self, current: ZoneKind | None) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold]BUILD[/]    [dim]d=denarii  t=timber  s=stone[/]\n")
            for hotkey, kind, label in _OPTIONS:
                marker = "[bright_green]*[/]" if kind == self._current else " "
                if kind is None:
                    yield Static(f"  {marker} [bright_yellow]{hotkey}[/]  {label}")
                else:
                    cost = _cost_string(kind)
                    yield Static(
                        f"  {marker} [bright_yellow]{hotkey}[/]  "
                        f"{label:<42} [grey70]{cost}[/]"
                    )
            yield Static("\n[dim]escape / b to cancel[/]")

    def action_pick(self, hotkey: str) -> None:
        for h, kind, _ in _OPTIONS:
            if h == hotkey:
                self.dismiss(kind)
                return

    def action_cancel(self) -> None:
        self.dismiss(self._current)
