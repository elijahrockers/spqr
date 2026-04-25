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
from spqr.ui.screens.build_menu import BuildMenuScreen
from spqr.ui.screens.info import GraphScreen, InfoResult, InfoScreen
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
    """

    BINDINGS = [
        Binding("space", "toggle_pause", "Pause"),
        Binding("plus,equals_sign,equal", "speed_up", "Faster"),
        Binding("minus", "speed_down", "Slower"),
        Binding("c", "view_city", "City"),
        Binding("r", "view_region", "Region"),
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
        Binding("l", "load", "Load"),
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

    def action_view_city(self) -> None:
        self.view_mode = "city"

    def action_view_region(self) -> None:
        # Drag is meaningful only on the city map.
        self._clear_drag()
        self.view_mode = "region"

    def action_cursor(self, dx: int, dy: int) -> None:
        if self._city_map is None or self.view_mode != "city":
            return
        self._city_map.move_cursor(dx, dy)

    def action_build_menu(self) -> None:
        # Pass the current tool so escape returns it unchanged. The callback
        # always treats the dismiss value as the new tool, even if it equals
        # the old one.
        self.push_screen(
            BuildMenuScreen(self._zone_tool), self._on_build_menu_dismissed
        )

    def _on_build_menu_dismissed(self, new_tool: ZoneKind | None) -> None:
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

    def action_cancel(self) -> None:
        """Escape: cancels in this priority — drag, then range highlight."""
        if self._drag_anchor is not None:
            self.action_cancel_drag()
            return
        if self._range_highlight is not None:
            self._clear_range_highlight()

    def action_place(self) -> None:
        if self._zone_tool is None or self._city_map is None:
            return
        if self.view_mode != "city":
            return
        cx, cy = self._city_map.cursor_x, self._city_map.cursor_y
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
