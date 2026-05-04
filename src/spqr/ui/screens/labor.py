"""Labor priority modal (`l`).

Shows the city's workforce — total / assigned / idle — and a
reorderable list of LaborCategory buckets. The order of the list
maps directly to City.labor_priority: top of the list is filled
first, bottom is filled last.

UX:
  ↑ / ↓   move the cursor up / down rows
  k       move the highlighted row up (raise priority)
  j       move the highlighted row down (lower priority)
  esc / l close — applies the new ordering on dismiss

Assignment counts refresh at ~5 Hz so the player can watch labor
shift between buckets while the engine ticks underneath.

Test approach: drive `action_*` directly. The screen never needs
a Textual pilot; mirrors `tests/test_splash.py` in spirit."""

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
    BUILDER_SLOTS,
    LaborCategory,
    labor_category_for,
)


REFRESH_HZ = 5


_CATEGORY_NAMES: dict[int, str] = {
    int(LaborCategory.CONSTRUCTION): "Construction",
    int(LaborCategory.FARMS):        "Farms",
    int(LaborCategory.LUMBER_MILLS): "Lumber mills",
    int(LaborCategory.QUARRIES):     "Quarries",
    int(LaborCategory.WORKSHOPS):    "Workshops",
    int(LaborCategory.OFFICES):      "Offices",
}


@dataclass(slots=True)
class LaborResult:
    """What LaborScreen sends back to the App.

    `priority` is the new ordering (a permutation of LaborCategory
    int values) when the player rearranged anything, else None to
    indicate "close — no change to apply." Letting the screen
    suppress no-op commands keeps the log clean and avoids replays
    of identity reorderings."""
    priority: list[int] | None


class _LaborBody(Widget):
    """Renders the live header + reorderable priority list. Lives on
    the modal so its render is the single source of truth for layout."""

    DEFAULT_CSS = """
    _LaborBody { height: auto; }
    """

    def __init__(
        self, state: GameState, screen: "LaborScreen", **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.screen_ref = screen

    def render(self) -> Text:
        return _render_report(self.state, self.screen_ref)


class LaborScreen(ModalScreen[LaborResult]):
    DEFAULT_CSS = """
    LaborScreen {
        align: center middle;
    }
    LaborScreen > Vertical {
        width: 64;
        height: auto;
        border: thick $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("up", "move_cursor(-1)", show=False),
        Binding("down", "move_cursor(1)", show=False),
        Binding("k", "reorder('up')", show=False),
        Binding("j", "reorder('down')", show=False),
        Binding("escape", "close", "Close"),
        Binding("l", "close", "Close"),
    ]

    def __init__(self, state: GameState) -> None:
        super().__init__()
        self.state = state
        self._initial_priority: list[int] = list(
            state.player_city().labor_priority
        )
        # Working draft. Mutated by action_reorder; applied (or not) on
        # dismiss based on whether it differs from the initial order.
        self._priority: list[int] = list(self._initial_priority)
        self._cursor: int = 0
        self._body: _LaborBody | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            self._body = _LaborBody(self.state, self)
            yield self._body

    def on_mount(self) -> None:
        self.set_interval(1.0 / REFRESH_HZ, self._tick)

    def _tick(self) -> None:
        if self._body is not None:
            self._body.refresh()

    def action_move_cursor(self, delta: int) -> None:
        new_pos = max(0, min(len(self._priority) - 1, self._cursor + delta))
        if new_pos == self._cursor:
            return
        self._cursor = new_pos
        if self._body is not None:
            self._body.refresh()

    def action_reorder(self, direction: str) -> None:
        """Move the highlighted row up (`'up'`) or down (`'down'`).
        The cursor follows the moved row so successive presses keep
        bumping the same bucket — same feel as moving items in most
        list widgets."""
        i = self._cursor
        if direction == "up" and i > 0:
            j = i - 1
        elif direction == "down" and i < len(self._priority) - 1:
            j = i + 1
        else:
            return
        self._priority[i], self._priority[j] = (
            self._priority[j], self._priority[i],
        )
        self._cursor = j
        if self._body is not None:
            self._body.refresh()

    def action_close(self) -> None:
        if self._priority == self._initial_priority:
            self.dismiss(LaborResult(priority=None))
            return
        self.dismiss(LaborResult(priority=list(self._priority)))


# --- rendering --------------------------------------------------------------


def _render_report(state: GameState, screen: LaborScreen) -> Text:
    city = state.player_city()
    text = Text()
    text.append("LABOR — ", style="bold")
    text.append(city.name.upper() + "\n", style="bold bright_yellow")
    text.append("─" * 40 + "\n\n", style="grey50")

    # Workforce summary
    workforce = sum(d.pops.workers() for d in city.districts)
    assigned = 0
    for b in city.buildings:
        if labor_category_for(b) is None:
            continue
        assigned += b.workers_assigned
    idle = max(0.0, workforce - assigned)
    text.append("  Workforce  ", style="grey70")
    text.append(f"{workforce:6.0f}\n", style="cyan")
    text.append("  Assigned   ", style="grey70")
    text.append(f"{assigned:6d}\n", style="green")
    text.append("  Idle       ", style="grey70")
    text.append(
        f"{idle:6.0f}\n", style="yellow" if idle > 0 else "white",
    )
    text.append("\n")

    # Priority list — ordered by the screen's working draft.
    counts = _category_assignments(city)
    text.append("Priority\n", style="bold")
    for row, cat_value in enumerate(screen._priority):
        is_cursor = row == screen._cursor
        marker = "►" if is_cursor else " "
        name = _CATEGORY_NAMES.get(cat_value, f"#{cat_value}")
        a, t = counts.get(cat_value, (0, 0))
        slot_color = (
            "green" if t > 0 and a == t else "yellow" if a > 0 else "grey50"
        )
        cursor_style = "bold bright_yellow" if is_cursor else "white"
        text.append(f"  {marker} {row + 1}. ", style=cursor_style)
        text.append(f"{name:<14}", style=cursor_style)
        text.append(f"{a:3d}/{t:<3d}", style=slot_color)
        text.append("\n")
    text.append("\n")

    text.append(
        "  ↑/↓ select   k/j reorder   esc close\n",
        style="dim",
    )
    return text


def _category_assignments(city) -> dict[int, tuple[int, int]]:
    """For each LaborCategory, return (assigned, total_slots) summed
    over the player city's buildings. `assigned` is the live
    `workers_assigned`; `total_slots` is what the bucket would draw at
    full staffing — BUILDER_SLOTS for under-construction, the
    operational slot count otherwise."""
    counts: dict[int, list[int]] = {
        int(c): [0, 0] for c in LaborCategory
    }
    for b in city.buildings:
        cat = labor_category_for(b)
        if cat is None:
            continue
        if b.is_under_construction:
            slots = BUILDER_SLOTS.get(b.kind, 1)
        else:
            slots = b.operational_worker_slots()
        counts[int(cat)][0] += b.workers_assigned
        counts[int(cat)][1] += slots
    return {k: (v[0], v[1]) for k, v in counts.items()}
