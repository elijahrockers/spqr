from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header

from spqr.engine.commands import (
    PlaceZoneRect,
    SetSpeed,
    TogglePause,
    ZoneKind,
)
from spqr.engine.events import LogSeverity, push_log
from spqr.engine.tick import Engine
from spqr.engine.world import SPEED_TICKS_PER_SEC, GameState, Speed
from spqr.persistence import load_from_path, save_to_path
from spqr.sim.systems import default_systems
from spqr.ui.screens.build_menu import (
    BuildCategoryScreen,
    BuildMenuResult,
    BuildMenuScreen,
)
from spqr.ui.screens.config import ConfigResult, ConfigScreen
from spqr.ui.screens.info import GraphScreen, InfoResult, InfoScreen
from spqr.ui.screens.labor import LaborResult, LaborScreen
from spqr.ui.screens.population import PopulationScreen
from spqr.ui.widgets.inspector import Inspector
from spqr.ui.widgets.log_panel import LogPanel
from spqr.ui.widgets.map_view import CityMap, RegionMap
from spqr.ui.widgets.status_bar import StatusBar


# How often the UI ticks the engine. Ticks-per-frame = ticks_per_sec / FRAME_HZ;
# fractional remainders are accumulated.
FRAME_HZ = 20
DEFAULT_SAVE_PATH = Path("saves/quick.spqr")


class SpqrApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        height: 1fr;
    }
    .map_holder {
        width: 3fr;
        border: solid $primary;
        padding: 0 1;
    }
    #right_col {
        width: 1fr;
    }
    LogPanel {
        height: 1fr;
    }
    Footer {
        background: black;
        color: white;
    }
    FooterKey {
        background: black;
        color: white;
    }
    FooterKey > .footer-key--key {
        background: black;
        color: ansi_bright_yellow;
        text-style: bold;
    }
    FooterKey > .footer-key--description {
        background: black;
        color: ansi_bright_white;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_pause", "Pause"),
        Binding("plus,equals_sign,equal", "speed_up", "Faster"),
        Binding("minus", "speed_down", "Slower"),
        Binding("r", "view_toggle", "Region/City"),
        Binding("c", "configure", "Configure"),
        Binding("up", "cursor(0,-1)", "↑", show=False),
        Binding("down", "cursor(0,1)", "↓", show=False),
        Binding("left", "cursor(-1,0)", "←", show=False),
        Binding("right", "cursor(1,0)", "→", show=False),
        Binding("b", "build_menu", "Build"),
        Binding("p", "population", "Pop"),
        Binding("i", "info", "Info"),
        Binding("enter", "place", "Place / commit drag"),
        Binding("escape", "cancel", "Cancel"),
        Binding("s", "save", "Save"),
        Binding("l", "labor", "Labor"),
        Binding("L", "load", "Load"),
        Binding("q", "quit", "Quit"),
    ]

    view_mode: reactive[str] = reactive("city")

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        self.title = "S P Q R"
        self.sub_title = engine.state.player_city().name
        self._tick_accum = 0.0
        self._zone_tool: ZoneKind | None = None
        self._drag_anchor: tuple[int, int] | None = None
        # When a granary is "highlight ranged," these tiles render with a
        # teal background. Set by the Info screen's (R) action; cleared
        # by escape from main view.
        self._range_highlight: frozenset[tuple[int, int]] | None = None
        self._range_highlight_owner: int | None = None
        # When a workshop / mill / quarry is "highlight ranged," these
        # tiles render with a red background — the nuisance zone.
        # Same lifecycle as range_highlight; cleared by escape.
        self._nuisance_highlight: frozenset[tuple[int, int]] | None = None
        self._nuisance_highlight_owner: int | None = None
        self._city_map: CityMap | None = None
        self._region_map: RegionMap | None = None
        self._status: StatusBar | None = None
        self._log_panel: LogPanel | None = None
        self._inspector: Inspector | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="main"):
            self._city_map = CityMap(
                self.engine.state, id="city_map", classes="map_holder"
            )
            self._region_map = RegionMap(
                self.engine.state, id="region_map", classes="map_holder"
            )
            self._region_map.display = False
            yield self._city_map
            yield self._region_map
            with Vertical(id="right_col"):
                self._inspector = Inspector(self.engine.state)
                yield self._inspector
                self._log_panel = LogPanel(self.engine.state)
                yield self._log_panel
        self._status = StatusBar(self.engine.state)
        yield self._status
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0 / FRAME_HZ, self._frame)

    def _frame(self) -> None:
        # Drain pending commands every frame so pause/speed changes apply
        # immediately even when the engine isn't stepping.
        self.engine.apply_pending()
        speed = self.engine.state.speed
        tps = SPEED_TICKS_PER_SEC[speed]
        self._tick_accum += tps / FRAME_HZ
        ticks_now = int(self._tick_accum)
        self._tick_accum -= ticks_now
        if ticks_now > 0:
            self.engine.step(ticks_now)
        self._refresh_widgets()

    def _refresh_widgets(self) -> None:
        # Update footprint preview before refreshing — when the OFFICE
        # tool is active, the cursor needs to show its 2×2 landing
        # zone in green (or red if blocked). Same idea for the nuisance
        # preview when an industrial tool is selected: red overlay
        # showing the would-be smoke/noise zone.
        if self._city_map is not None:
            self._city_map.pending_footprint = self._compute_pending_footprint()
            self._city_map.nuisance_highlight = self._compute_nuisance_overlay()
        if self._city_map is not None and self._city_map.display:
            self._city_map.refresh()
        if self._region_map is not None and self._region_map.display:
            self._region_map.refresh()
        if self._status is not None:
            self._status.refresh()
        if self._log_panel is not None:
            self._log_panel.refresh()
        if self._inspector is not None and self._city_map is not None:
            self._inspector.set_cursor(
                self._city_map.cursor_x, self._city_map.cursor_y
            )

    def _compute_pending_footprint(self) -> frozenset[tuple[int, int]] | None:
        """Tiles to highlight as the active brush's landing zone.
        Returns None unless a fixed-shape tool is selected. OFFICE is
        the only one today; future multi-tile builds plug in here."""
        if self._city_map is None or self._zone_tool is None:
            return None
        if self._zone_tool != ZoneKind.OFFICE:
            return None
        from spqr.sim.models import OFFICE_FOOTPRINT_H, OFFICE_FOOTPRINT_W

        cx, cy = self._city_map.cursor_x, self._city_map.cursor_y
        return frozenset(
            (cx + dx, cy + dy)
            for dy in range(OFFICE_FOOTPRINT_H)
            for dx in range(OFFICE_FOOTPRINT_W)
        )

    def _compute_nuisance_overlay(self) -> frozenset[tuple[int, int]] | None:
        """Composite nuisance overlay: union of the sticky info-screen
        highlight (set when the player presses 'r' on a workshop / mill
        / quarry's info modal) and the live placement preview (when
        an industrial tool is the active brush). Either or both may
        be set; returning None tells the map to draw no overlay."""
        if self._city_map is None:
            return None
        sticky = self._nuisance_highlight or frozenset()
        live = frozenset()
        if self._zone_tool in (
            ZoneKind.WORKSHOP, ZoneKind.LUMBER_MILL, ZoneKind.QUARRY,
        ):
            from spqr.engine.tick import _ZONE_TO_BUILDING
            from spqr.sim.systems.housing import nuisance_tiles_for_kind_at

            cx, cy = self._city_map.cursor_x, self._city_map.cursor_y
            kind = _ZONE_TO_BUILDING[self._zone_tool]
            live = frozenset(
                nuisance_tiles_for_kind_at(
                    self.engine.state.player_city(), kind, cx, cy
                )
            )
        if not sticky and not live:
            return None
        return sticky | live

    def watch_view_mode(self, mode: str) -> None:
        if self._city_map is None or self._region_map is None:
            return
        self._city_map.display = mode == "city"
        self._region_map.display = mode == "region"

    # --- actions -----------------------------------------------------------

    def action_toggle_pause(self) -> None:
        self.engine.submit(TogglePause())

    def action_speed_up(self) -> None:
        s = self.engine.state.speed
        self.engine.submit(SetSpeed(min(int(Speed.FASTEST), int(s) + 1)))

    def action_speed_down(self) -> None:
        s = self.engine.state.speed
        self.engine.submit(SetSpeed(max(int(Speed.PAUSED), int(s) - 1)))

    def action_view_toggle(self) -> None:
        if self.view_mode == "region":
            self.view_mode = "city"
        else:
            # Drag is meaningful only on the city map.
            self._clear_drag()
            self.view_mode = "region"

    def action_cursor(self, dx: int, dy: int) -> None:
        if self._city_map is None or self.view_mode != "city":
            return
        self._city_map.move_cursor(dx, dy)

    def action_build_menu(self) -> None:
        # Pass the current tool so escape returns it unchanged. The
        # top-level callback handles either a "tool" pick (set the
        # brush) or a "category" pick (open submenu).
        self.push_screen(
            BuildMenuScreen(self._zone_tool),
            self._on_build_menu_dismissed,
        )

    def _on_build_menu_dismissed(self, result: BuildMenuResult | None) -> None:
        if result is None:
            return
        if result.kind == "category" and result.category is not None:
            # Top-level picked a category; open the matching submenu.
            # The submenu's callback feeds back into _set_zone_tool,
            # so two cancels are needed to fully back out (one to
            # dismiss the submenu, one to dismiss the top — but our
            # submenu cancel returns the current tool unchanged, so
            # there's nothing to undo).
            self.push_screen(
                BuildCategoryScreen(result.category, self._zone_tool),
                self._set_zone_tool,
            )
            return
        # kind == "tool"
        self._set_zone_tool(result.tool)

    def _set_zone_tool(self, new_tool: ZoneKind | None) -> None:
        if new_tool == self._zone_tool:
            return
        self._zone_tool = new_tool
        # An in-progress drag belongs to the previous tool; drop it.
        self._clear_drag()
        if self._status is not None:
            self._status.zone_kind = new_tool
            self._status.drag_anchor = None
            self._status.refresh()

    def action_population(self) -> None:
        self.push_screen(PopulationScreen(self.engine.state))

    def action_labor(self) -> None:
        self.push_screen(
            LaborScreen(self.engine.state),
            self._on_labor_dismissed,
        )

    def _on_labor_dismissed(self, result: LaborResult | None) -> None:
        if result is None or result.priority is None:
            return
        from spqr.engine.commands import SetLaborPriority

        self.engine.submit(SetLaborPriority(result.priority))

    def action_info(self) -> None:
        if self._city_map is None or self.view_mode != "city":
            return
        city = self.engine.state.player_city()
        x, y = self._city_map.cursor_x, self._city_map.cursor_y
        if not city.in_bounds(x, y):
            return
        tile = city.tile(x, y)
        if tile.building_id == -1:
            return
        self.push_screen(
            InfoScreen(self.engine.state, tile.building_id),
            self._on_info_dismissed,
        )

    def _on_info_dismissed(self, result: InfoResult | None) -> None:
        if result is None or result.kind == "close":
            return
        if result.kind == "highlight" and result.granary_id is not None:
            self._set_range_highlight(result.granary_id)
        elif result.kind == "graph" and result.granary_id is not None:
            self.push_screen(
                GraphScreen(self.engine.state, result.granary_id)
            )
        elif result.kind == "nuisance" and result.nuisance_id is not None:
            self._set_nuisance_highlight(result.nuisance_id)

    def action_configure(self) -> None:
        if self._city_map is None or self.view_mode != "city":
            return
        city = self.engine.state.player_city()
        x, y = self._city_map.cursor_x, self._city_map.cursor_y
        if not city.in_bounds(x, y):
            return
        tile = city.tile(x, y)
        if tile.building_id == -1:
            return
        self.push_screen(
            ConfigScreen(self.engine.state, tile.building_id),
            self._on_config_dismissed,
        )

    def _on_config_dismissed(self, result: ConfigResult | None) -> None:
        if result is None or result.kind == "close":
            return
        if result.kind == "set_crop" and result.farm_id is not None:
            from spqr.engine.commands import SetFarmCrop

            self.engine.submit(SetFarmCrop(result.farm_id, int(result.crop)))
        elif (
            result.kind == "set_tier_cap"
            and result.building_id is not None
            and result.tier_cap is not None
        ):
            from spqr.engine.commands import SetResidenceTierCap

            self.engine.submit(
                SetResidenceTierCap(result.building_id, result.tier_cap)
            )
        elif (
            result.kind == "set_good"
            and result.building_id is not None
            and result.good is not None
        ):
            from spqr.engine.commands import SetWorkshopGood

            self.engine.submit(
                SetWorkshopGood(result.building_id, int(result.good))
            )
        elif (
            result.kind == "set_warehouse_caps"
            and result.building_id is not None
            and result.cap_timber is not None
            and result.cap_stone is not None
            and result.cap_vegetables is not None
            and result.cap_furniture is not None
            and result.cap_stoneware is not None
        ):
            from spqr.engine.commands import SetWarehouseCaps

            self.engine.submit(
                SetWarehouseCaps(
                    result.building_id,
                    result.cap_timber,
                    result.cap_stone,
                    result.cap_vegetables,
                    result.cap_furniture,
                    result.cap_stoneware,
                )
            )

    def _set_range_highlight(self, granary_id: int) -> None:
        from spqr.sim.models import GRANARY_REACH_COST
        from spqr.sim.systems.spatial import coverage

        city = self.engine.state.player_city()
        granary = city.buildings[granary_id]
        cov = coverage(city, granary.x, granary.y, GRANARY_REACH_COST)
        self._range_highlight = frozenset(cov.keys())
        self._range_highlight_owner = granary_id
        if self._city_map is not None:
            self._city_map.range_highlight = self._range_highlight
            self._city_map.refresh()
        push_log(
            self.engine.state.log,
            self.engine.state.tick,
            LogSeverity.INFO,
            f"Highlighting granary range at ({granary.x},{granary.y}). "
            "Press escape to clear.",
        )

    def _clear_range_highlight(self) -> None:
        self._range_highlight = None
        self._range_highlight_owner = None
        if self._city_map is not None:
            self._city_map.range_highlight = None
            self._city_map.refresh()

    def _set_nuisance_highlight(self, building_id: int) -> None:
        from spqr.sim.systems.housing import nuisance_tiles_for

        city = self.engine.state.player_city()
        b = city.buildings[building_id]
        tiles = nuisance_tiles_for(city, b)
        self._nuisance_highlight = frozenset(tiles)
        self._nuisance_highlight_owner = building_id
        if self._city_map is not None:
            self._city_map.nuisance_highlight = self._nuisance_highlight
            self._city_map.refresh()
        push_log(
            self.engine.state.log,
            self.engine.state.tick,
            LogSeverity.INFO,
            f"Highlighting {b.kind.name.lower().replace('_', ' ')} nuisance "
            f"at ({b.x},{b.y}). Press escape to clear.",
        )

    def _clear_nuisance_highlight(self) -> None:
        self._nuisance_highlight = None
        self._nuisance_highlight_owner = None
        if self._city_map is not None:
            self._city_map.nuisance_highlight = None
            self._city_map.refresh()

    def action_cancel(self) -> None:
        """Escape: cancels in this priority — drag, then range
        highlight, then nuisance highlight, then the active build tool.
        Clearing the tool last gives the player a Vim-style reset; with
        nothing in the way, escape drops the brush back to nothing."""
        if self._drag_anchor is not None:
            self.action_cancel_drag()
            return
        if self._range_highlight is not None:
            self._clear_range_highlight()
            return
        if self._nuisance_highlight is not None:
            self._clear_nuisance_highlight()
            return
        if self._zone_tool is not None:
            self._set_zone_tool(None)

    def action_place(self) -> None:
        if self._zone_tool is None or self._city_map is None:
            return
        if self.view_mode != "city":
            return
        cx, cy = self._city_map.cursor_x, self._city_map.cursor_y
        # Office is a fixed 2×2 footprint; no rectangle drag. Fire the
        # placement immediately on the first Enter press.
        if self._zone_tool == ZoneKind.OFFICE:
            self.engine.submit(
                PlaceZoneRect(x1=cx, y1=cy, x2=cx, y2=cy, kind=ZoneKind.OFFICE)
            )
            return
        if self._drag_anchor is None:
            # First press: set the anchor; the rectangle preview will follow
            # the cursor until enter is pressed again or escape cancels.
            self._drag_anchor = (cx, cy)
            self._city_map.drag_anchor = (cx, cy)
            if self._status is not None:
                self._status.drag_anchor = (cx, cy)
                self._status.refresh()
            self._city_map.refresh()
            return
        ax, ay = self._drag_anchor
        self.engine.submit(
            PlaceZoneRect(x1=ax, y1=ay, x2=cx, y2=cy, kind=self._zone_tool)
        )
        self._clear_drag()

    def action_cancel_drag(self) -> None:
        if self._drag_anchor is None:
            return
        self._clear_drag()
        push_log(
            self.engine.state.log,
            self.engine.state.tick,
            LogSeverity.INFO,
            "Designation cancelled.",
        )

    def _clear_drag(self) -> None:
        self._drag_anchor = None
        if self._city_map is not None:
            self._city_map.drag_anchor = None
            self._city_map.refresh()
        if self._status is not None:
            self._status.drag_anchor = None
            self._status.refresh()

    def action_save(self) -> None:
        self.engine.capture_rng()
        save_to_path(self.engine.state, DEFAULT_SAVE_PATH)
        push_log(
            self.engine.state.log,
            self.engine.state.tick,
            LogSeverity.GOOD,
            f"Saved to {DEFAULT_SAVE_PATH}.",
        )

    def action_load(self) -> None:
        if not DEFAULT_SAVE_PATH.exists():
            push_log(
                self.engine.state.log,
                self.engine.state.tick,
                LogSeverity.WARNING,
                f"No save at {DEFAULT_SAVE_PATH}.",
            )
            return
        loaded = load_from_path(DEFAULT_SAVE_PATH)
        new_engine = Engine(loaded, default_systems())
        self.engine = new_engine
        # Rebind widgets to the new state.
        if self._city_map is not None:
            self._city_map.state = loaded
        if self._region_map is not None:
            self._region_map.state = loaded
        if self._status is not None:
            self._status.state = loaded
        if self._log_panel is not None:
            self._log_panel.state = loaded


def run_app(state: GameState) -> None:
    engine = Engine(state, default_systems())
    SpqrApp(engine).run()
