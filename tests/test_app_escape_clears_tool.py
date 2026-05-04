"""Tests for the Vim-style escape behavior in `SpqrApp.action_cancel`.

The handler cascades through three states:
  1. drag in progress → cancel drag
  2. range highlight visible → clear highlight
  3. neither → clear the active build tool

Drives `action_cancel` directly with the app instance; doesn't need a
Textual pilot."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.systems import default_systems
from spqr.ui.app import SpqrApp


def _make_app():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    return SpqrApp(eng)


def test_escape_clears_tool_when_no_drag_or_highlight():
    app = _make_app()
    app._zone_tool = ZoneKind.FARM
    assert app._drag_anchor is None
    assert app._range_highlight is None
    app.action_cancel()
    assert app._zone_tool is None


def test_escape_clears_drag_first_leaving_tool_intact():
    """With both a drag in progress and a tool selected, escape
    should cancel the drag but leave the tool active — that's the
    'undo my last placement step' shortcut."""
    app = _make_app()
    app._zone_tool = ZoneKind.FARM
    app._drag_anchor = (5, 5)
    app.action_cancel()
    assert app._drag_anchor is None
    assert app._zone_tool == ZoneKind.FARM


def test_escape_clears_highlight_before_tool():
    """With a range highlight visible (no drag), escape clears the
    highlight first. Tool stays active so the player can resume."""
    app = _make_app()
    app._zone_tool = ZoneKind.ROAD
    app._range_highlight = frozenset({(1, 1), (1, 2)})
    app._range_highlight_owner = 0
    app.action_cancel()
    assert app._range_highlight is None
    assert app._zone_tool == ZoneKind.ROAD


def test_escape_with_no_state_is_noop():
    """No drag, no highlight, no tool — escape doesn't error or
    spuriously change anything."""
    app = _make_app()
    assert app._zone_tool is None
    assert app._drag_anchor is None
    assert app._range_highlight is None
    app.action_cancel()
    assert app._zone_tool is None
    assert app._drag_anchor is None
    assert app._range_highlight is None
