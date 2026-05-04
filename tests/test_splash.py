"""Tests for the pre-game SplashApp.

Drives `action_choose` directly to verify each hotkey resolves to
the expected exit value. Mirrors the testing approach used by
`tests/test_build_menu.py` and `tests/test_config_screen.py` —
no Textual pilot needed."""

from __future__ import annotations

from spqr.ui.splash import SplashApp


def test_n_chooses_new_city():
    app = SplashApp()
    captured: list[object] = []
    app.exit = lambda result=None, **kw: captured.append(result)  # type: ignore[assignment]
    app.action_choose("new")
    assert captured == ["new"]


def test_e_chooses_existing_village():
    app = SplashApp()
    captured: list[object] = []
    app.exit = lambda result=None, **kw: captured.append(result)  # type: ignore[assignment]
    app.action_choose("existing")
    assert captured == ["existing"]


def test_q_chooses_quit():
    app = SplashApp()
    captured: list[object] = []
    app.exit = lambda result=None, **kw: captured.append(result)  # type: ignore[assignment]
    app.action_choose("quit")
    assert captured == ["quit"]


def test_splash_title_static_renders_without_markup_leak():
    """The splash uses `Static` widgets, which auto-parse Rich markup —
    no chance of `[bright_yellow]` leaking. But pin the title shape so
    a future refactor doesn't accidentally drop the placeholder logo."""
    from spqr.ui.splash import _TITLE

    assert "█" in _TITLE  # ASCII block letters present


def test_option_row_format_matches_build_menu_style():
    """Splash option rows reuse the build-menu's hotkey/label/description
    layout. Pin the structure so the splash and build menus stay
    visually consistent."""
    from spqr.ui.splash import _option_row

    row = _option_row("n", "New city", "empty terrain")
    assert "[bright_yellow]n[/]" in row
    assert "New city" in row
    assert "empty terrain" in row
