"""Pre-game splash screen: title plus a small chooser for the
starting world. Returns one of the choice strings via `app.exit()` so
`run_splash()` can hand the answer back to the CLI before it bootstraps
the game state.

Choices:
  - "new"      — empty terrain; player builds from scratch
  - "existing" — the production default 11×3 starter block (today's
                 `seed_starter=True` behaviour)
  - "quit"     — exit without launching the game

ASCII title is a placeholder; real logo art lives here when it ships.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static


# Big ASCII placeholder for the eventual logo. Block-letter "SPQR"
# in classic-ish style.
_TITLE = r"""
 ███████╗██████╗  ██████╗ ██████╗
 ██╔════╝██╔══██╗██╔═══██╗██╔══██╗
 ███████╗██████╔╝██║   ██║██████╔╝
 ╚════██║██╔═══╝ ██║▄▄ ██║██╔══██╗
 ███████║██║     ╚██████╔╝██║  ██║
 ╚══════╝╚═╝      ╚══▀▀═╝ ╚═╝  ╚═╝
"""


class SplashApp(App[str]):
    """Tiny Textual app: shows the title + choice menu, exits with the
    chosen string. Returned via `app.run()` to the CLI caller."""

    CSS = """
    SplashApp {
        align: center middle;
    }
    SplashApp > Vertical {
        width: 70;
        height: auto;
        border: thick $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("n", "choose('new')", show=False),
        Binding("e", "choose('existing')", show=False),
        Binding("q", "choose('quit')", show=False),
        Binding("escape", "choose('quit')", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(_TITLE, id="splash_title")
            yield Static(
                "[bold bright_white]Roman City Simulation Engine[/]"
            )
            yield Static("[grey50]" + "─" * 64 + "[/]")
            yield Static("")
            yield Static(
                _option_row("n", "New city",
                            "empty terrain — build from scratch")
            )
            yield Static(
                _option_row("e", "Existing village",
                            "small starter block (default)")
            )
            yield Static("")
            yield Static(
                _option_row("q", "Quit", "exit to terminal")
            )
            yield Static("")
            yield Static("[dim]escape also quits[/]")

    def action_choose(self, what: str) -> None:
        # `App.exit(value)` ends the app and makes `run()` return value.
        self.exit(what)


def _option_row(hotkey: str, name: str, description: str) -> str:
    """One row in the choice list. Mirrors the build-menu styling so
    the splash and main menus feel like part of the same toolset."""
    return (
        f"  [bright_yellow]{hotkey}[/]  "
        f"[bright_white]{name:<18}[/] [grey50]{description}[/]"
    )


def run_splash() -> str | None:
    """Show the splash and block until the user picks something.
    Returns the choice string ("new" / "existing" / "quit") or None
    if the runtime didn't produce a return value (e.g. terminal
    closed unexpectedly)."""
    return SplashApp().run()
