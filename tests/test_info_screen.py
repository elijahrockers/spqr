"""Tests for the (i)nfo workflow: history recording, info modal,
range highlight, and the inventory graph. Also covers the residence
info section that took over from the inspector for granary/warehouse
listings."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import BuildingKind, GRANARY_HISTORY_MAX_SAMPLES
from spqr.sim.systems import default_systems
from spqr.ui.screens.info import (
    InfoResult,
    _render_graph,
    _render_granary_info,
    _render_residence_info,
)

from ._helpers import bootstrap_starter_city


def test_granary_history_records_per_tick():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    # Fresh granary just got recorded by the bootstrap step; clear history
    # to start the count clean.
    granary.inventory_history = []
    eng.step(10)
    # Each step appends one sample.
    assert len(granary.inventory_history) == 10
    # The most recent sample matches current grain_stored.
    assert granary.inventory_history[-1] == granary.grain_stored


def test_granary_history_caps_at_max_samples():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    eng.step(GRANARY_HISTORY_MAX_SAMPLES + 100)
    assert len(granary.inventory_history) == GRANARY_HISTORY_MAX_SAMPLES


def test_render_granary_info_lists_served_buildings():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    text = str(_render_granary_info(state, city, granary))
    assert "GRANARY INFO" in text
    assert "Reach:" in text
    assert "Serves:" in text


def test_render_graph_hourly_mode():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    eng.step(48)
    text = str(_render_graph(granary, daily=False))
    assert "GRANARY INVENTORY" in text
    assert "hourly" in text
    assert "Window:" in text


def test_render_graph_daily_mode_aggregates_24h_chunks():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    # Run for 3 days so we have 3 daily-aggregate samples.
    eng.step(72)
    text = str(_render_graph(granary, daily=True))
    assert "daily" in text
    # Three days of hourly samples → 3 daily aggregates.
    assert "3 days" in text


def test_render_graph_handles_empty_history():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    # Reset history to empty so the renderer's empty path is hit.
    granary.inventory_history = []
    text = str(_render_graph(granary, daily=False))
    assert "no history" in text


def test_info_result_is_a_three_state_enum():
    """The Info modal returns one of three results: close, highlight, graph.
    Crop changes moved off the info screen to the configure screen, so
    cycle_crop is no longer part of this enum."""
    a = InfoResult(kind="close")
    b = InfoResult(kind="highlight", granary_id=3)
    c = InfoResult(kind="graph", granary_id=5)
    assert a.granary_id is None
    assert b.granary_id == 3
    assert c.kind == "graph"


def test_render_residence_info_lists_granaries_and_warehouses_in_reach():
    """The granary/warehouse listing migrated from the inspector — make
    sure the same per-source detail lands in the (i) panel for residences."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]
    text = str(_render_residence_info(city, house))
    assert "RESIDENCE INFO" in text
    assert "Granaries in reach:" in text
    assert "Warehouses in reach:" in text
    # Should show the bootstrap granary's stocks.
    granary = handles["granary"]
    assert f"({granary.x},{granary.y})" in text
    # Variety / road indicators present.
    assert "Food types:" in text
    assert "Road within" in text


def test_render_residence_info_marks_no_food_in_reach():
    """A residence without any granary or warehouse in reach should
    say so explicitly — that's the whole point of moving the detail
    out of the inspector."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    # Place a residence in isolation; no granary or warehouse anywhere.
    from ._helpers import find_clear_grass

    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.RESIDENCE))
    eng.step(1)
    house = next(b for b in city.buildings if b.kind == BuildingKind.RESIDENCE)
    text = str(_render_residence_info(city, house))
    assert "none in reach" in text
