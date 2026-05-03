"""Configuration modal — bound to the 'c' hotkey on the main map.

Per building kind, presents the configurable options:
  - FARM: which crop is sown. Switching past CROP_SWITCH_CONFIRM_THRESHOLD
    maturity prompts y/n confirmation since standing growth is discarded.
  - RESIDENCE: tier ceiling. The housing system stops upgrading once
    the residence reaches `tier_cap`. Useful for keeping a low-density
    neighborhood (huts/cottages) from densifying into insulae even
    when materials and roads are available.
  - WORKSHOP: which good is produced. Furniture consumes timber;
    stoneware consumes stone. Switching is instant.

Other building kinds open with a "nothing to configure" hint so the
dialog is still discoverable everywhere."""

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
    RESIDENCE_MAX_TIER,
    RESIDENCE_TIER_CAPACITY,
    RESIDENCE_TIER_NAME,
    BuildingKind,
    Crop,
    Good,
)


# Confirm before switching crops if the standing growth is past this
# fraction of maturity. Below the threshold, switching is silent.
CROP_SWITCH_CONFIRM_THRESHOLD: float = 0.30


@dataclass(slots=True)
class ConfigResult:
    """Returned by ConfigScreen on dismiss.

    `kind` is one of:
      "close"        — modal dismissed; no further action
      "set_crop"     — App should apply `crop` to the farm `farm_id`
      "set_tier_cap" — App should set RESIDENCE `building_id`'s
                       tier_cap to `tier_cap`
      "set_good"     — App should set WORKSHOP `building_id`'s good
                       to `good`
    """
    kind: str
    farm_id: int | None = None
    crop: Crop | None = None
    building_id: int | None = None
    tier_cap: int | None = None
    good: Good | None = None


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
        if b.kind == BuildingKind.RESIDENCE:
            return _render_residence_config(b)
        if b.kind == BuildingKind.WORKSHOP:
            return _render_workshop_config(b)
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

    # Character hotkeys instead of numeric. Same dispatcher routes
    # both crop selection (FARM: w=wheat, v=vegetables) and tier-cap
    # selection (RESIDENCE: u=undeveloped, h=huts, o=cOttages, i=insula).
    # `c`-close conflicts with cottages; `o` (second letter) avoids it.
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("c", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel_pending", "Cancel", show=False),
        # Farm crop picker
        Binding("w", "pick_char('w')", show=False),
        Binding("v", "pick_char('v')", show=False),
        # Residence tier-cap picker
        Binding("u", "pick_char('u')", show=False),
        Binding("h", "pick_char('h')", show=False),
        Binding("o", "pick_char('o')", show=False),
        Binding("i", "pick_char('i')", show=False),
        # Workshop good picker
        Binding("f", "pick_char('f')", show=False),
        Binding("s", "pick_char('s')", show=False),
    ]

    # Character hotkey → crop / tier_cap / good value. Source of truth
    # for both the binding handlers and the renderers.
    _FARM_KEY_TO_CROP: dict[str, "Crop"] = {
        "w": Crop.WHEAT,
        "v": Crop.VEGETABLES,
    }
    _RESIDENCE_KEY_TO_TIER_CAP: dict[str, int] = {
        "u": 0,  # undeveloped
        "h": 1,  # huts
        "o": 2,  # cOttages
        "i": 3,  # insula (uncapped)
    }
    _WORKSHOP_KEY_TO_GOOD: dict[str, "Good"] = {
        "f": Good.FURNITURE,
        "s": Good.STONEWARE,
    }

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

    def _is_residence(self) -> bool:
        b = self.state.player_city().buildings[self.building_id]
        return b.kind == BuildingKind.RESIDENCE

    def _is_workshop(self) -> bool:
        b = self.state.player_city().buildings[self.building_id]
        return b.kind == BuildingKind.WORKSHOP

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

    def action_pick_char(self, key: str) -> None:
        """Character-key dispatcher. Routes by building kind:
          - FARM: w=wheat, v=vegetables
          - RESIDENCE: u/h/o/i = undeveloped/huts/cottages/insula
          - WORKSHOP: f=furniture, s=stoneware
        Keys irrelevant to the focused building kind are no-ops."""
        if self._is_farm():
            crop = self._FARM_KEY_TO_CROP.get(key)
            if crop is None:
                return
            self._select_crop(crop)
            return
        if self._is_residence():
            cap = self._RESIDENCE_KEY_TO_TIER_CAP.get(key)
            if cap is None:
                return
            self._select_tier_cap(cap)
            return
        if self._is_workshop():
            good = self._WORKSHOP_KEY_TO_GOOD.get(key)
            if good is None:
                return
            self._select_good(good)

    def _select_crop(self, new_crop: Crop) -> None:
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

    def _select_tier_cap(self, new_cap: int) -> None:
        b = self.state.player_city().buildings[self.building_id]
        if b.tier_cap == new_cap:
            self.dismiss(ConfigResult(kind="close"))
            return
        self.dismiss(
            ConfigResult(
                kind="set_tier_cap",
                building_id=self.building_id,
                tier_cap=new_cap,
            )
        )

    def _select_good(self, new_good: Good) -> None:
        b = self.state.player_city().buildings[self.building_id]
        if int(b.good) == int(new_good):
            self.dismiss(ConfigResult(kind="close"))
            return
        self.dismiss(
            ConfigResult(
                kind="set_good",
                building_id=self.building_id,
                good=new_good,
            )
        )

    # Compatibility shim for unit tests that drive crop selection
    # directly. Routes through `_select_crop` so behavior stays
    # identical to the binding path.
    def action_pick_crop(self, crop_value: str) -> None:
        if not self._is_farm():
            return
        self._select_crop(Crop(int(crop_value)))

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
        crop_to_key = {Crop.WHEAT: "w", Crop.VEGETABLES: "v"}
        for crop in Crop:
            is_current = int(crop) == int(b.crop)
            hotkey = crop_to_key[crop]
            text.append("  ")
            if is_current:
                text.append("*", style="bright_green")
            else:
                text.append(" ")
            text.append(" ")
            text.append(hotkey, style="bright_yellow")
            text.append(f"  {crop.name.lower()}\n")
        text.append("\nescape / c to close\n", style="dim")
    else:
        text.append("  Switching to ", style="grey70")
        text.append(f"{pending.name.lower()}", style="bright_yellow")
        text.append(" will discard the\n  current ", style="grey70")
        text.append(f"{pct}% mature ", style="yellow")
        text.append(f"{current.name.lower()} crop.\n\n", style="grey70")
        text.append("  ")
        text.append("Y", style="bright_yellow")
        text.append("  Confirm switch\n")
        text.append("  ")
        text.append("N", style="bright_yellow")
        text.append("  Cancel\n")
    return text


def _render_residence_config(b) -> Text:  # type: ignore[no-untyped-def]
    text = Text()
    text.append("CONFIGURE RESIDENCE\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")
    text.append(f"  Position:  ({b.x}, {b.y})\n", style="grey70")
    current_name = RESIDENCE_TIER_NAME.get(b.tier, "?")
    text.append("  Tier:      ", style="grey70")
    text.append(
        f"{current_name} ({b.tier}/{RESIDENCE_MAX_TIER})\n", style="bright_yellow"
    )
    cap_name = RESIDENCE_TIER_NAME.get(b.tier_cap, "?")
    text.append("  Cap:       ", style="grey70")
    if b.tier_cap >= RESIDENCE_MAX_TIER:
        text.append("none — will keep upgrading\n", style="green")
    else:
        text.append(f"{cap_name} ({b.tier_cap}/{RESIDENCE_MAX_TIER})\n", style="yellow")
    text.append("\n  Pick a tier ceiling:\n\n")
    # Hotkeys: first letter where unique. `o` for cottages avoids the
    # `c`-close conflict; `i` for insula doubles as "uncapped".
    tier_to_key = {0: "u", 1: "h", 2: "o", 3: "i"}
    for tier in range(RESIDENCE_MAX_TIER + 1):
        tier_name = RESIDENCE_TIER_NAME.get(tier, "?")
        capacity = RESIDENCE_TIER_CAPACITY.get(tier, 0)
        is_current_cap = tier == b.tier_cap
        hotkey = tier_to_key.get(tier, str(tier))
        text.append("  ")
        if is_current_cap:
            text.append("*", style="bright_green")
        else:
            text.append(" ")
        text.append(" ")
        text.append(hotkey, style="bright_yellow")
        text.append(f"  {tier_name:<12}")
        text.append(f"  cap {capacity}", style="grey50")
        if tier == RESIDENCE_MAX_TIER:
            text.append("  (uncapped)", style="grey50")
        text.append("\n")
    text.append("\nescape / c to close\n", style="dim")
    return text


def _render_workshop_config(b) -> Text:  # type: ignore[no-untyped-def]
    from spqr.sim.models import (
        WORKSHOP_INPUT_PER_WORKER_PER_TICK,
        WORKSHOP_OUTPUT_PER_WORKER_PER_TICK,
    )

    text = Text()
    text.append("CONFIGURE WORKSHOP\n", style="bold")
    text.append("─" * 40 + "\n\n", style="grey50")
    text.append(f"  Position:  ({b.x}, {b.y})\n", style="grey70")
    current = Good(b.good)
    text.append("  Good:      ", style="grey70")
    text.append(f"{current.name.lower()}\n", style="bright_yellow")
    input_per_tick = WORKSHOP_INPUT_PER_WORKER_PER_TICK
    output_per_tick = WORKSHOP_OUTPUT_PER_WORKER_PER_TICK
    text.append(
        f"  Rate:      {input_per_tick:.2f} in / {output_per_tick:.2f} out per worker/hr\n\n",
        style="grey50",
    )
    text.append("  Pick a good:\n\n")
    good_to_key = {Good.FURNITURE: "f", Good.STONEWARE: "s"}
    good_to_input = {Good.FURNITURE: "timber", Good.STONEWARE: "stone"}
    for good in Good:
        is_current = int(good) == int(b.good)
        hotkey = good_to_key[good]
        text.append("  ")
        if is_current:
            text.append("*", style="bright_green")
        else:
            text.append(" ")
        text.append(" ")
        text.append(hotkey, style="bright_yellow")
        text.append(f"  {good.name.lower():<12}")
        text.append(f"  consumes {good_to_input[good]}", style="grey50")
        text.append("\n")
    text.append("\nescape / c to close\n", style="dim")
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
    text.append("\nescape / c to close\n", style="dim")
    return text
