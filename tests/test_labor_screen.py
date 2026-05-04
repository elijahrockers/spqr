"""Tests for the LaborScreen modal — drives action handlers
directly. Mirrors `tests/test_splash.py` in spirit: no Textual pilot
needed."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.sim.models import LaborCategory
from spqr.ui.screens.labor import LaborResult, LaborScreen


def _make_screen():
    state = new_game(seed=42, seed_starter=False)
    screen = LaborScreen(state)
    captured: list[object] = []
    screen.dismiss = (
        lambda result=None, **kw: captured.append(result)  # type: ignore[assignment]
    )
    return state, screen, captured


def test_screen_starts_with_default_priority():
    state, screen, _captured = _make_screen()
    expected = list(state.player_city().labor_priority)
    assert screen._priority == expected
    assert screen._cursor == 0


def test_move_cursor_clamps_to_list_bounds():
    state, screen, _captured = _make_screen()
    screen.action_move_cursor(-1)  # already at 0; should clamp
    assert screen._cursor == 0
    screen.action_move_cursor(1)
    assert screen._cursor == 1
    # Walk past the bottom.
    for _ in range(20):
        screen.action_move_cursor(1)
    assert screen._cursor == len(screen._priority) - 1


def test_reorder_up_swaps_with_neighbor_above():
    """k (reorder('up')) swaps the highlighted row with its predecessor
    and follows the moved entry — successive presses keep promoting
    the same bucket until it hits the top."""
    state, screen, _captured = _make_screen()
    # Default order: [CONSTRUCTION, FARMS, LUMBER_MILLS, QUARRIES,
    # WORKSHOPS, OFFICES]. Park cursor on QUARRIES (idx 3) and bump up.
    screen._cursor = 3
    initial = list(screen._priority)
    screen.action_reorder("up")
    expected = list(initial)
    expected[3], expected[2] = expected[2], expected[3]
    assert screen._priority == expected
    assert screen._cursor == 2  # cursor follows the moved row


def test_reorder_down_swaps_with_neighbor_below():
    state, screen, _captured = _make_screen()
    screen._cursor = 0
    initial = list(screen._priority)
    screen.action_reorder("down")
    expected = list(initial)
    expected[0], expected[1] = expected[1], expected[0]
    assert screen._priority == expected
    assert screen._cursor == 1


def test_reorder_at_top_is_noop():
    state, screen, _captured = _make_screen()
    screen._cursor = 0
    initial = list(screen._priority)
    screen.action_reorder("up")
    assert screen._priority == initial
    assert screen._cursor == 0


def test_reorder_at_bottom_is_noop():
    state, screen, _captured = _make_screen()
    screen._cursor = len(screen._priority) - 1
    initial = list(screen._priority)
    screen.action_reorder("down")
    assert screen._priority == initial


def test_close_unchanged_dismisses_with_none_priority():
    state, screen, captured = _make_screen()
    screen.action_close()
    assert len(captured) == 1
    result = captured[0]
    assert isinstance(result, LaborResult)
    assert result.priority is None


def test_close_after_reorder_dismisses_with_new_priority():
    state, screen, captured = _make_screen()
    initial = list(screen._priority)
    screen.action_reorder("down")
    new_order = list(screen._priority)
    assert new_order != initial
    screen.action_close()
    assert len(captured) == 1
    result = captured[0]
    assert isinstance(result, LaborResult)
    assert result.priority == new_order


def test_priority_is_a_permutation_of_six_values():
    """Whatever the screen returns, it must be a permutation of
    LaborCategory values 0..5 — the engine handler validates this and
    silently drops anything else."""
    state, screen, captured = _make_screen()
    screen.action_reorder("down")
    screen.action_reorder("down")
    screen.action_close()
    result = captured[0]
    expected = sorted(int(c) for c in LaborCategory)
    assert result is not None
    assert sorted(result.priority) == expected
