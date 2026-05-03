"""Configuration modal — bound to the 'c' hotkey on the main map.

Per building kind, presents the configurable options. Today only farms
have anything to configure (which crop is sown). Other kinds open with a
"nothing to configure" hint so the dialog is still discoverable.

For a farm, picking a different crop confirms first if the standing crop
is more than CROP_SWITCH_CONFIRM_THRESHOLD mature — switching away
discards in-progress growth, which is annoying if it's almost ripe."""

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
    Crop,
)


# Confirm before switching crops if the standing growth is past this
# fraction of maturity. Below the threshold, switching is silent.
CROP_SWITCH_CONFIRM_THRESHOLD: float = 0.30


@dataclass(slots=True)
class ConfigResult:
    """Returned by ConfigScreen on dismiss.

    `kind` is one of:
      "close"    — modal dismissed; no further action
      "set_crop" — App should apply `crop` to the farm `farm_id`
    """
    kind: str
    farm_id: int | None = None
    crop: Crop | None = None


class _ConfigBody(Widget):
    DEFAULT_CSS = """
    _ConfigBody { height: auto; }
    """

    def __init__(
        self,
        state: GameState,
        building_id: int,
        pending_crop: Crop | None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.building_id = building_id
        self.pending_crop = pending_crop

    def render(self) -> Text:
        city = self.state.player_city()
        b = city.buildings[self.building_id]
        if b.kind == BuildingKind.FARM:
            return _render_farm_config(b, self.pending_crop)
        return _render_no_config(b)


class ConfigScreen(ModalScreen[ConfigResult]):
    """The 'c' hotkey opens this. Farms route to crop selection; other
    kinds show a placeholder."""

    DEFAULT_CSS = """
    ConfigScreen {
        align: center middle;
    }
    ConfigScreen > Vertical {
        width: 60;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("c", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("1", "pick_crop('0')", "Wheat", show=False),
        Binding("2", "pick_crop('1')", "Vegetables", show=False),
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel_pending", "Cancel", show=False),
    ]

    def __init__(self, state: GameState, building_id: int) -> None:
        super().__init__()
        self.state = state
        self.building_id = building_id
        # When a crop switch needs confirmation, we stash the requested
        # crop here and wait for y/n.
        self._pending_crop: Crop | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield _ConfigBody(self.state, self.building_id, self._pending_crop)

    def _is_farm(self) -> bool:
        b = self.state.player_city().buildings[self.building_id]
        return b.kind == BuildingKind.FARM

    def _refresh(self) -> None:
        # Modal may not be mounted in unit tests that drive actions
        # directly; query_one raises in that case. Guard so the action
        # paths stay testable without a Textual app pilot.
        try:
            body = self.query_one(_ConfigBody)
        except Exception:
            return
        body.pending_crop = self._pending_crop
        body.refresh()

    def action_close(self) -> None:
        self.dismiss(ConfigResult(kind="close"))

    def action_pick_crop(self, crop_value: str) -> None:
        if not self._is_farm():
            return
        new_crop = Crop(int(crop_value))
        b = self.state.player_city().buildings[self.building_id]
        if int(b.crop) == int(new_crop):
            # No-op selection; just close.
            self.dismiss(ConfigResult(kind="close"))
            return
        if b.grain_maturity > CROP_SWITCH_CONFIRM_THRESHOLD:
            # Stash and ask for y/n before applying.
            self._pending_crop = new_crop
            self._refresh()
            return
        self.dismiss(
            ConfigResult(kind="set_crop", farm_id=self.building_id, crop=new_crop)
        )

    def action_confirm(self) -> None:
        if self._pending_crop is None:
            return
        self.dismiss(
            ConfigResult(
                kind="set_crop",
                farm_id=self.building_id,
                crop=self._pending_crop,
            )
        )

    def action_cancel_pending(self) -> None:
        if self._pending_crop is None:
            return
        self._pending_crop = None
        self._refresh()


def _render_farm_config(b, pending: Crop | None) -> Text:  # type: ignore[no-untyped-def]
    text = Text()
    text.append("CONFIGURE FARM\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")
    text.append(f"  Position:  ({b.x}, {b.y})\n", style="grey70")
    current = Crop(b.crop)
    text.append("  Crop:      ", style="grey70")
    text.append(f"{current.name.lower()}", style="bright_yellow")
    text.append(
        f"  ({int(b.farm_yield_per_harvest())} per harvest)\n", style="grey50"
    )
    pct = int(b.grain_maturity * 100)
    text.append("  Maturity:  ", style="grey70")
    color = "yellow" if b.grain_maturity > CROP_SWITCH_CONFIRM_THRESHOLD else "grey70"
    text.append(f"{pct}%\n\n", style=color)

    if pending is None:
        text.append("  Pick a crop:\n\n")
        for crop in Crop:
            marker = "[bright_green]*[/]" if int(crop) == int(b.crop) else " "
            hotkey = "1" if crop == Crop.WHEAT else "2"
            text.append(
                f"  {marker} [bright_yellow]{hotkey}[/]  {crop.name.lower()}\n"
            )
        text.append("\n[dim]escape / c to close[/]\n")
    else:
        text.append(
            f"  Switching to ", style="grey70"
        )
        text.append(f"{pending.name.lower()}", style="bright_yellow")
        text.append(" will discard the\n  current ", style="grey70")
        text.append(f"{pct}% mature ", style="yellow")
        text.append(f"{current.name.lower()} crop.\n\n", style="grey70")
        text.append("  [bright_yellow]Y[/]  Confirm switch\n")
        text.append("  [bright_yellow]N[/]  Cancel\n")
    return text


def _render_no_config(b) -> Text:  # type: ignore[no-untyped-def]
    text = Text()
    text.append("CONFIGURE\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")
    text.append(f"  {b.kind.name.title()}", style="bold bright_white")
    text.append(f"   ({b.x}, {b.y})\n\n", style="grey50")
    text.append(
        "  Nothing to configure for this building kind.\n",
        style="grey70",
    )
    text.append("\n[dim]escape / c to close[/]\n")
    return text
