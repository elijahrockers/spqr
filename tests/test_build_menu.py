"""Tests for the BuildMenuScreen / BuildCategoryScreen flow.

The top-level menu dismisses with a `BuildMenuResult`. Direct picks
return kind="tool"; category picks return kind="category" so the App
can chain into the right submenu."""

from __future__ import annotations

from spqr.engine.commands import ZoneKind
from spqr.ui.screens.build_menu import (
    CATEGORY_INFRASTRUCTURE,
    CATEGORY_PRODUCTION,
    BuildCategoryScreen,
    BuildMenuResult,
    BuildMenuScreen,
)


# --- Top level --------------------------------------------------------------

def test_top_level_R_picks_residence_directly():
    screen = BuildMenuScreen(current=None)
    captured: list[BuildMenuResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_residence()
    assert len(captured) == 1
    assert captured[0].kind == "tool"
    assert captured[0].tool == ZoneKind.RESIDENCE


def test_top_level_p_opens_production_category():
    screen = BuildMenuScreen(current=None)
    captured: list[BuildMenuResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_category(CATEGORY_PRODUCTION)
    assert len(captured) == 1
    assert captured[0].kind == "category"
    assert captured[0].category == CATEGORY_PRODUCTION


def test_top_level_i_opens_infrastructure_category():
    screen = BuildMenuScreen(current=None)
    captured: list[BuildMenuResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_category(CATEGORY_INFRASTRUCTURE)
    assert len(captured) == 1
    assert captured[0].kind == "category"
    assert captured[0].category == CATEGORY_INFRASTRUCTURE


def test_top_level_0_clears_tool():
    screen = BuildMenuScreen(current=ZoneKind.FARM)
    captured: list[BuildMenuResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_clear_tool()
    assert captured[0].kind == "tool"
    assert captured[0].tool is None


def test_top_level_escape_preserves_current_tool():
    """Escape should leave the brush untouched. The dismiss carries
    the current tool back so the App's compare-to-old equality check
    is a no-op."""
    screen = BuildMenuScreen(current=ZoneKind.FARM)
    captured: list[BuildMenuResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_cancel()
    assert captured[0].kind == "tool"
    assert captured[0].tool == ZoneKind.FARM


# --- Production submenu -----------------------------------------------------

def test_production_submenu_picks_known_keys():
    screen = BuildCategoryScreen(CATEGORY_PRODUCTION, current=None)
    captured: list[ZoneKind | None] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    # Spot-check several production hotkeys.
    screen.action_pick("f")
    assert captured[-1] == ZoneKind.FARM
    screen2 = BuildCategoryScreen(CATEGORY_PRODUCTION, current=None)
    screen2.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen2.action_pick("o")
    assert captured[-1] == ZoneKind.OFFICE


def test_production_submenu_ignores_infrastructure_keys():
    """`r` is the road hotkey (infrastructure); pressing it inside
    the production submenu must be a no-op, not a stray dismiss."""
    screen = BuildCategoryScreen(CATEGORY_PRODUCTION, current=None)
    captured: list[ZoneKind | None] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick("r")
    assert len(captured) == 0


# --- Infrastructure submenu -------------------------------------------------

def test_infrastructure_submenu_picks_road():
    screen = BuildCategoryScreen(CATEGORY_INFRASTRUCTURE, current=None)
    captured: list[ZoneKind | None] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick("r")
    assert captured[0] == ZoneKind.ROAD


def test_infrastructure_submenu_ignores_production_keys():
    screen = BuildCategoryScreen(CATEGORY_INFRASTRUCTURE, current=None)
    captured: list[ZoneKind | None] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick("f")  # farm — wrong category
    assert len(captured) == 0


def test_submenu_escape_returns_current_tool():
    screen = BuildCategoryScreen(CATEGORY_PRODUCTION, current=ZoneKind.GRANARY)
    captured: list[ZoneKind | None] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_cancel()
    assert captured[0] == ZoneKind.GRANARY
