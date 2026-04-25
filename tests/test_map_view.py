"""Visual rendering tests for the city map."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import BuildingKind, CityTerrain
from spqr.sim.systems import default_systems
from spqr.ui.widgets.map_view import (
    BUILDING_GLYPH,
    CITY_TERRAIN_GLYPH,
    _render_city,
)


def test_construction_site_flash_alternates_glyph():
    """An under-construction building should render as the building glyph
    in one phase and as the underlying terrain glyph in the other."""
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Zone a farm on a known empty grass tile so we can read the tile back.
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 10_000.0
    city.treasury.stone = 10_000.0
    spot = None
    for y in range(city.height):
        for x in range(city.width):
            t = city.tile(x, y)
            if t.building_id == -1 and t.terrain == CityTerrain.GRASS:
                spot = (x, y)
                break
        if spot:
            break
    assert spot is not None
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.FARM))
    eng.step(1)
    new_b = city.buildings[-1]
    assert new_b.completion < 1.0  # under construction

    # Render with each phase explicitly. The character at the construction
    # tile should differ between phases.
    text_with_building = _render_city(
        city, 0, 0, None, flash_show_building=True
    )
    text_with_terrain = _render_city(
        city, 0, 0, None, flash_show_building=False
    )
    bx, by = spot
    # Each row in the rendered text ends in a newline, so the offset of
    # tile (x, y) is `y * (width + 1) + x`.
    idx = by * (city.width + 1) + bx
    s1 = str(text_with_building)
    s2 = str(text_with_terrain)
    farm_glyph = BUILDING_GLYPH[BuildingKind.FARM][0]
    grass_glyph = CITY_TERRAIN_GLYPH[CityTerrain.GRASS][0]
    assert s1[idx] == farm_glyph
    assert s2[idx] == grass_glyph


def test_completed_building_does_not_flash():
    """A finished building shows its glyph in both flash phases — only
    construction sites alternate."""
    state = new_game(seed=42)
    city = state.player_city()
    # Find a completed FORUM placed by procgen.
    forum = next(
        b for b in city.buildings
        if b.kind == BuildingKind.FORUM and b.completion >= 1.0
    )
    s1 = str(_render_city(city, 0, 0, None, flash_show_building=True))
    s2 = str(_render_city(city, 0, 0, None, flash_show_building=False))
    idx = forum.y * (city.width + 1) + forum.x
    forum_glyph = BUILDING_GLYPH[BuildingKind.FORUM][0]
    assert s1[idx] == forum_glyph
    assert s2[idx] == forum_glyph
