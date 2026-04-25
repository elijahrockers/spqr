"""Tests for the (i)nfo workflow: history recording, info modal,
range highlight, and the inventory graph."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BuildingKind,
    GRANARY_HISTORY_MAX_SAMPLES,
)
from spqr.sim.systems import default_systems
from spqr.ui.screens.info import (
    InfoResult,
    _render_graph,
    _render_granary_info,
)


def test_granary_history_records_per_tick():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    granary = next(
        b for b in state.player_city().buildings
        if b.kind == BuildingKind.GRANARY
    )
    assert granary.inventory_history == []
    eng.step(10)
    # Each step appends one sample.
    assert len(granary.inventory_history) == 10
    # The most recent sample matches current grain_stored.
    assert granary.inventory_history[-1] == granary.grain_stored


def test_granary_history_caps_at_max_samples():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    granary = next(
        b for b in state.player_city().buildings
        if b.kind == BuildingKind.GRANARY
    )
    eng.step(GRANARY_HISTORY_MAX_SAMPLES + 100)
    assert len(granary.inventory_history) == GRANARY_HISTORY_MAX_SAMPLES


def test_render_granary_info_lists_served_buildings():
    state = new_game(seed=42)
    city = state.player_city()
    granary = next(
        b for b in city.buildings if b.kind == BuildingKind.GRANARY
    )
    text = str(_render_granary_info(state, city, granary))
    assert "GRANARY INFO" in text
    assert "Reach:" in text
    assert "Serves:" in text


def test_render_graph_hourly_mode():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    eng.step(48)
    granary = next(
        b for b in state.player_city().buildings
        if b.kind == BuildingKind.GRANARY
    )
    text = str(_render_graph(granary, daily=False))
    assert "GRANARY INVENTORY" in text
    assert "hourly" in text
    assert "Window:" in text


def test_render_graph_daily_mode_aggregates_24h_chunks():
    state = new_game(seed=42)
    eng = Engine(state, default_systems())
    # Run for 3 days so we have 3 daily-aggregate samples.
    eng.step(72)
    granary = next(
        b for b in state.player_city().buildings
        if b.kind == BuildingKind.GRANARY
    )
    text = str(_render_graph(granary, daily=True))
    assert "daily" in text
    # Three days of hourly samples → 3 daily aggregates.
    assert "3 days" in text


def test_render_graph_handles_empty_history():
    state = new_game(seed=42)
    granary = next(
        b for b in state.player_city().buildings
        if b.kind == BuildingKind.GRANARY
    )
    # No steps taken; history is empty.
    text = str(_render_graph(granary, daily=False))
    assert "no history" in text


def test_info_result_is_a_three_state_enum():
    """The Info modal returns one of three results: close, highlight, graph."""
    a = InfoResult(kind="close")
    b = InfoResult(kind="highlight", granary_id=3)
    c = InfoResult(kind="graph", granary_id=5)
    assert a.granary_id is None
    assert b.granary_id == 3
    assert c.kind == "graph"
