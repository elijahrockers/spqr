from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from spqr.engine.world import GameState, Speed
from spqr.engine.commands import ZoneKind


SPEED_LABEL = {
    Speed.PAUSED: "PAUSED",
    Speed.NORMAL: "1x",
    Speed.FAST: "4x",
    Speed.FASTER: "16x",
    Speed.FASTEST: "64x",
}


class StatusBar(Widget):
    """Single-line status bar: date, treasury, pop, speed, current zone tool."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $boost;
        color: $text;
    }
    """

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.zone_kind: ZoneKind | None = None
        self.drag_anchor: tuple[int, int] | None = None

    def render(self) -> Text:
        s = self.state
        city = s.player_city()
        y, mo, day = s.date()
        pops = sum(d.pops.total() for d in city.districts)
        tool = self.zone_kind.name.lower() if self.zone_kind else "none"
        if self.drag_anchor is not None:
            ax, ay = self.drag_anchor
            tool = f"{tool} (anchor {ax},{ay} — enter to commit, esc to cancel)"
        return Text.from_markup(
            f"[bold]{city.name}[/]  "
            f"AUC {y} {mo:02d}/{day:02d} {s.hour():02d}:00  "
            f"[yellow]grain {city.treasury.grain:6.0f}[/]  "
            f"[bright_yellow]den {city.treasury.denarii:6.0f}[/]  "
            f"[cyan]pop {pops:5.0f}[/]  "
            f"speed [{('red' if s.speed == Speed.PAUSED else 'green')}]{SPEED_LABEL[s.speed]}[/]  "
            f"tool [magenta]{tool}[/]"
        )
