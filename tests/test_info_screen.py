"""Tests for the (i)nfo workflow: history recording, info modal,
range highlight, and the inventory graph."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.sim.models import GRANARY_HISTORY_MAX_SAMPLES
from spqr.sim.systems import default_systems
from spqr.ui.screens.info import (
    InfoResult,
    _render_graph,
    _render_granary_info,
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
    """The Info modal returns one of three results: close, highlight, graph."""
    a = InfoResult(kind="close")
    b = InfoResult(kind="highlight", granary_id=3)
    c = InfoResult(kind="graph", granary_id=5)
    assert a.granary_id is None
    assert b.granary_id == 3
    assert c.kind == "graph"
