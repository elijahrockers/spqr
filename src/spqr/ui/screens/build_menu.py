"""Build-tool menus.

Two screens:

- `BuildMenuScreen` (top level) shows the categories and the direct
  Residence pick. Dismisses with a `BuildMenuResult`: a `ZoneKind` (or
  `None` for clear) the App should adopt, OR a category sentinel the
  App should open as a submenu.

- `BuildCategoryScreen(category, current)` shows the buildings in one
  category (Production or Infrastructure). Dismisses with `ZoneKind`
  or `None`.

The App chains them: dismissed top-level result that names a category
triggers a `push_screen(BuildCategoryScreen(...))`; the submenu's
final dismiss feeds back into the same `_on_build_menu_dismissed`
handler that direct picks use.

Visual polish: each modal has a colored header indicating breadcrumb,
hotkeys in bright_yellow, building names in bright_white, costs in
grey50. The current selection (if any) is marked with a bright_green
asterisk so the player can see what's already on the brush."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from spqr.engine.commands import ZoneKind
from spqr.sim.models import BUILDING_COST, BuildingKind


# Category sentinels — used as the `category` payload on
# BuildMenuResult and as the discriminator in
# BuildCategoryScreen.__init__.
CATEGORY_PRODUCTION = "production"
CATEGORY_INFRASTRUCTURE = "infrastructure"


@dataclass(slots=True)
class BuildMenuResult:
    """Top-level dismiss payload.

    `kind` is one of:
      "tool"      — the App should set the brush to `tool` (a
                    ZoneKind, or None for clear).
      "category"  — the App should open a submenu for `category`.
    """
    kind: str
    tool: ZoneKind | None = None
    category: str | None = None


_ZONE_TO_BUILDING: dict[ZoneKind, BuildingKind] = {
    ZoneKind.FARM: BuildingKind.FARM,
    ZoneKind.RESIDENCE: BuildingKind.RESIDENCE,
    ZoneKind.GRANARY: BuildingKind.GRANARY,
    ZoneKind.WORKSHOP: BuildingKind.WORKSHOP,
    ZoneKind.ROAD: BuildingKind.ROAD,
    ZoneKind.WAREHOUSE: BuildingKind.WAREHOUSE,
    ZoneKind.LUMBER_MILL: BuildingKind.LUMBER_MILL,
    ZoneKind.QUARRY: BuildingKind.QUARRY,
    ZoneKind.OFFICE: BuildingKind.OFFICE,
}


def _cost_string(zone: ZoneKind) -> str:
    # Destructive tools (UNDESIGNATE, BULLDOZE) don't designate a
    # building, so they have no BUILDING_COST entry. Show their fee
    # via the override table instead.
    if zone in _TOOL_COST_OVERRIDE:
        return _TOOL_COST_OVERRIDE[zone]
    cost = BUILDING_COST[_ZONE_TO_BUILDING[zone]]
    parts = []
    if cost.denarii:
        parts.append(f"{int(cost.denarii)}d")
    if cost.timber:
        parts.append(f"{int(cost.timber)}t")
    if cost.stone:
        parts.append(f"{int(cost.stone)}s")
    return " ".join(parts) if parts else "free"


# Category contents. Each entry: (hotkey, ZoneKind, label).
_PRODUCTION_OPTIONS: list[tuple[str, ZoneKind, str]] = [
    ("f", ZoneKind.FARM,        "Farm        — wheat (up to 3 workers); switch crop with c"),
    ("g", ZoneKind.GRANARY,     "Granary     — grain storage (2 workers)"),
    ("W", ZoneKind.WAREHOUSE,   "Warehouse   — materials + vegetables storage"),
    ("L", ZoneKind.LUMBER_MILL, "Lumber mill — timber from forests (2 workers)"),
    ("Q", ZoneKind.QUARRY,      "Quarry      — stone (2 workers, requires timber)"),
    ("w", ZoneKind.WORKSHOP,    "Workshop    — furniture or stoneware (4 workers)"),
    ("o", ZoneKind.OFFICE,      "Office      — admin reach + tax (2×2 footprint)"),
]

_INFRASTRUCTURE_OPTIONS: list[tuple[str, ZoneKind, str]] = [
    ("r", ZoneKind.ROAD,        "Road        — connects tiles, extends reach"),
    ("u", ZoneKind.UNDESIGNATE, "Undesignate — cancel construction (full refund)"),
    ("z", ZoneKind.BULLDOZE,    "Bulldoze    — demolish (10d, salvage 50% materials)"),
]


# Tools without a BUILDING_COST entry get an explicit cost label here.
_TOOL_COST_OVERRIDE: dict[ZoneKind, str] = {
    ZoneKind.UNDESIGNATE: "free",
    ZoneKind.BULLDOZE: "10d",
}


_MODAL_CSS = """
$modal {
    align: center middle;
}
$modal > Vertical {
    width: 76;
    height: auto;
    border: thick $accent;
    padding: 1 2;
    background: $surface;
}
"""


# --- Top-level menu --------------------------------------------------------


class BuildMenuScreen(ModalScreen[BuildMenuResult]):
    """Top-level: pick a category or the direct Residence brush."""

    DEFAULT_CSS = _MODAL_CSS.replace("$modal", "BuildMenuScreen")

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("b", "cancel", "Cancel"),
        Binding("R", "pick_residence", show=False),
        Binding("p", "category('production')", show=False),
        Binding("i", "category('infrastructure')", show=False),
        Binding("0", "clear_tool", show=False),
    ]

    def __init__(self, current: ZoneKind | None) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "[bold bright_white]BUILD[/]    "
                "[grey50]d=denarii  t=timber  s=stone[/]"
            )
            yield Static("[grey50]" + "─" * 70 + "[/]")
            yield Static(
                _row("R", "Residence", _cost_string(ZoneKind.RESIDENCE),
                     marker_active=self._current == ZoneKind.RESIDENCE)
            )
            yield Static(
                _category_row("p", "Production",
                              "farm, granary, mill, quarry, workshop, …")
            )
            yield Static(
                _category_row("i", "Infrastructure",
                              "roads (wells, gardens to come)")
            )
            yield Static(_clear_row(self._current is None))
            yield Static("")
            yield Static("[dim]escape / b — close[/]")

    def action_cancel(self) -> None:
        # Preserve the current tool if the player escapes.
        self.dismiss(BuildMenuResult(kind="tool", tool=self._current))

    def action_pick_residence(self) -> None:
        self.dismiss(BuildMenuResult(kind="tool", tool=ZoneKind.RESIDENCE))

    def action_clear_tool(self) -> None:
        self.dismiss(BuildMenuResult(kind="tool", tool=None))

    def action_category(self, name: str) -> None:
        self.dismiss(BuildMenuResult(kind="category", category=name))


# --- Category submenu ------------------------------------------------------


class BuildCategoryScreen(ModalScreen[ZoneKind | None]):
    """Per-category: pick a building from this category. Escape returns
    the current tool unchanged so cancelling out doesn't lose it."""

    DEFAULT_CSS = _MODAL_CSS.replace("$modal", "BuildCategoryScreen")

    # The full superset of category hotkeys is bound here; the action
    # handler dispatches by the active category's option list.
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("b", "cancel", "Cancel"),
        # Production
        Binding("f", "pick('f')", show=False),
        Binding("g", "pick('g')", show=False),
        Binding("W", "pick('W')", show=False),
        Binding("L", "pick('L')", show=False),
        Binding("Q", "pick('Q')", show=False),
        Binding("w", "pick('w')", show=False),
        Binding("o", "pick('o')", show=False),
        # Infrastructure
        Binding("r", "pick('r')", show=False),
        Binding("u", "pick('u')", show=False),
        Binding("z", "pick('z')", show=False),
    ]

    def __init__(self, category: str, current: ZoneKind | None) -> None:
        super().__init__()
        self._category = category
        self._current = current

    def compose(self) -> ComposeResult:
        title, options, color = _category_meta(self._category)
        with Vertical():
            yield Static(
                f"[bold bright_white]BUILD[/] [grey50]»[/] [bold {color}]{title}[/]"
            )
            yield Static("[grey50]" + "─" * 70 + "[/]")
            for hotkey, kind, label in options:
                yield Static(
                    _row(hotkey, label, _cost_string(kind),
                         marker_active=kind == self._current)
                )
            yield Static("")
            yield Static("[dim]escape / b — back[/]")

    def action_cancel(self) -> None:
        self.dismiss(self._current)

    def action_pick(self, hotkey: str) -> None:
        _title, options, _color = _category_meta(self._category)
        for h, kind, _label in options:
            if h == hotkey:
                self.dismiss(kind)
                return
        # Hotkey not in this category — silently no-op (e.g. user
        # presses a production key while in the infrastructure menu).


# --- Rendering helpers -----------------------------------------------------


def _row(hotkey: str, label: str, cost: str, *, marker_active: bool) -> str:
    """One menu row, markup for Static. The leading marker shows
    whether this option matches the current brush."""
    marker = "[bright_green]*[/]" if marker_active else " "
    return (
        f"  {marker} [bright_yellow]{hotkey}[/]  "
        f"[bright_white]{label:<48}[/] [grey50]{cost}[/]"
    )


def _category_row(hotkey: str, name: str, summary: str) -> str:
    """Top-level category row, with a » to indicate it opens a submenu."""
    return (
        f"    [bright_yellow]{hotkey}[/]  "
        f"[bold bright_cyan]{name:<14}[/] [grey50]» {summary}[/]"
    )


def _clear_row(active: bool) -> str:
    marker = "[bright_green]*[/]" if active else " "
    return (
        f"  {marker} [bright_yellow]0[/]  "
        f"[grey70]Clear current tool[/]"
    )


def _category_meta(
    category: str,
) -> tuple[str, list[tuple[str, ZoneKind, str]], str]:
    if category == CATEGORY_PRODUCTION:
        return ("Production", _PRODUCTION_OPTIONS, "bright_yellow")
    if category == CATEGORY_INFRASTRUCTURE:
        return ("Infrastructure", _INFRASTRUCTURE_OPTIONS, "bright_cyan")
    raise ValueError(f"unknown build category: {category!r}")
