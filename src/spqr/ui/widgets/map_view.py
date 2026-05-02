"""Tilemap renderers for the city and region views.

These widgets read directly from GameState (passed in by the parent screen)
and re-render on demand. They are deliberately stateless aside from the
camera cursor — all simulation state lives on GameState."""

from __future__ import annotations

import time

from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from spqr.engine.world import GameState
from spqr.sim.models import (
    BuildingKind,
    City,
    CityTerrain,
    Province,
    RegionBiome,
    SiteKind,
)


# Glyph + color per city terrain.
CITY_TERRAIN_GLYPH: dict[CityTerrain, tuple[str, str]] = {
    CityTerrain.GRASS: (".", "green"),
    CityTerrain.DIRT: (".", "yellow"),
    CityTerrain.FOREST: ("T", "dark_green"),
    CityTerrain.HILL: ("^", "tan"),
    CityTerrain.WATER: ("~", "blue"),
    CityTerrain.ROCK: ("#", "grey50"),
    CityTerrain.ROAD: ("=", "grey70"),
}

# Glyph + color per building kind. Construction-in-progress is rendered dim.
BUILDING_GLYPH: dict[BuildingKind, tuple[str, str]] = {
    BuildingKind.FORUM: ("F", "bright_magenta"),
    BuildingKind.INSULA: ("h", "bright_white"),
    BuildingKind.DOMUS: ("H", "bright_white"),
    BuildingKind.FARM: ("f", "yellow"),
    BuildingKind.GRANARY: ("G", "yellow"),
    BuildingKind.WORKSHOP: ("W", "cyan"),
    BuildingKind.TEMPLE: ("t", "bright_yellow"),
    BuildingKind.ROAD: ("=", "grey70"),
    BuildingKind.WAREHOUSE: ("S", "bright_cyan"),
}

REGION_BIOME_GLYPH: dict[RegionBiome, tuple[str, str]] = {
    RegionBiome.SEA: ("~", "blue"),
    RegionBiome.RIVER: ("~", "bright_blue"),
    RegionBiome.PLAIN: (".", "green"),
    RegionBiome.HILL: ("^", "tan"),
    RegionBiome.FOREST: ("T", "dark_green"),
    RegionBiome.MOUNTAIN: ("M", "grey70"),
    RegionBiome.MARSH: (",", "dark_olive_green3"),
}

# Under-construction tiles flash between the building glyph and the
# underlying terrain glyph. Each phase lasts this many seconds.
_FLASH_PHASE_SECONDS = 0.5


class CityMap(Widget):
    """Renders the player city's tilemap with a movable cursor and an
    optional drag-rectangle preview."""

    cursor_x: reactive[int] = reactive(0)
    cursor_y: reactive[int] = reactive(0)

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        city = state.player_city()
        self.cursor_x = city.width // 2
        self.cursor_y = city.height // 2
        # When set, render a preview rectangle from this anchor to the cursor.
        self.drag_anchor: tuple[int, int] | None = None
        # When set, these tiles render with a teal "in range" background.
        self.range_highlight: frozenset[tuple[int, int]] | None = None

    def render(self) -> Text:
        return _render_city(
            self.state.player_city(),
            self.cursor_x,
            self.cursor_y,
            self.drag_anchor,
            range_highlight=self.range_highlight,
        )

    def move_cursor(self, dx: int, dy: int) -> None:
        city = self.state.player_city()
        self.cursor_x = max(0, min(city.width - 1, self.cursor_x + dx))
        self.cursor_y = max(0, min(city.height - 1, self.cursor_y + dy))
        self.refresh()


class RegionMap(Widget):
    """Renders the regional map with site icons."""

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state

    def render(self) -> Text:
        return _render_region(self.state.province)


def _render_city(
    city: City,
    cur_x: int,
    cur_y: int,
    drag_anchor: tuple[int, int] | None = None,
    *,
    flash_show_building: bool | None = None,
    range_highlight: frozenset[tuple[int, int]] | None = None,
) -> Text:
    """Render the city tilemap. Pass `flash_show_building` explicitly in
    tests; in production it's derived from the wall clock so construction
    sites animate even while the sim is paused."""
    # Importing locally to avoid a top-level cycle (engine -> models, ui ->
    # engine via the app entry point).
    from spqr.engine.tick import is_buildable

    if flash_show_building is None:
        flash_show_building = (
            int(time.monotonic() / _FLASH_PHASE_SECONDS) % 2
        ) == 0

    if drag_anchor is not None:
        ax, ay = drag_anchor
        rx_lo, rx_hi = min(ax, cur_x), max(ax, cur_x)
        ry_lo, ry_hi = min(ay, cur_y), max(ay, cur_y)
    else:
        rx_lo = ry_lo = rx_hi = ry_hi = -1

    text = Text(no_wrap=True)
    for y in range(city.height):
        for x in range(city.width):
            tile = city.tiles[y * city.width + x]
            terrain_glyph, terrain_color = CITY_TERRAIN_GLYPH[tile.terrain]
            glyph, color = terrain_glyph, terrain_color
            if tile.building_id != -1:
                b = city.buildings[tile.building_id]
                if b.completion < 1.0:
                    # Alternate: half the time show the building glyph (dim),
                    # the other half let the underlying terrain show.
                    if flash_show_building:
                        bg, bc = BUILDING_GLYPH[b.kind]
                        glyph, color = bg, "grey50"
                    # else: keep terrain glyph from above
                else:
                    glyph, color = BUILDING_GLYPH[b.kind]
            style = Style(color=color)
            # Range highlight underlies drag and cursor — drag/cursor wins.
            if range_highlight is not None and (x, y) in range_highlight:
                style = Style(color=color, bgcolor="dark_cyan")
            in_rect = (
                drag_anchor is not None
                and rx_lo <= x <= rx_hi
                and ry_lo <= y <= ry_hi
            )
            if in_rect:
                # Green = will place here; red = will be skipped.
                bg = "dark_green" if is_buildable(city, x, y) else "dark_red"
                style = Style(color=color, bgcolor=bg)
            if x == cur_x and y == cur_y:
                style = Style(color="black", bgcolor="white", bold=True)
            elif drag_anchor is not None and (x, y) == drag_anchor:
                style = Style(color="black", bgcolor="bright_yellow", bold=True)
            text.append(glyph, style=style)
        text.append("\n")
    return text


def _render_region(province: Province) -> Text:
    text = Text(no_wrap=True)
    site_lookup: dict[tuple[int, int], SiteKind] = {
        (s.region_y, s.region_x): s.kind for s in province.sites
    }
    for y in range(province.height):
        for x in range(province.width):
            tile = province.tiles[y * province.width + x]
            kind = site_lookup.get((y, x))
            if kind == SiteKind.PLAYER_CITY:
                text.append("@", style=Style(color="bright_yellow", bold=True))
                continue
            if tile.has_road:
                text.append("=", style=Style(color="grey70"))
                continue
            glyph, color = REGION_BIOME_GLYPH[tile.biome]
            text.append(glyph, style=Style(color=color))
        text.append("\n")
    return text
