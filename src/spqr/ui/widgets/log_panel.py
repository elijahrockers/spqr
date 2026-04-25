from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from spqr.engine.events import LogSeverity
from spqr.engine.world import GameState


SEVERITY_COLOR = {
    LogSeverity.INFO: "white",
    LogSeverity.GOOD: "green",
    LogSeverity.WARNING: "yellow",
    LogSeverity.BAD: "red",
}


class LogPanel(Widget):
    DEFAULT_CSS = """
    LogPanel {
        border: solid $secondary;
        height: 100%;
    }
    """

    def __init__(self, state: GameState, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.border_title = "Annals"

    def render(self) -> Text:
        text = Text()
        recent = self.state.log[-20:]
        for entry in recent:
            year, mo, day = self._date_for(entry.tick)
            color = SEVERITY_COLOR[entry.severity]
            text.append(f"{year} {mo:02d}/{day:02d}  ", style="grey50")
            text.append(entry.text + "\n", style=color)
        return text

    def _date_for(self, tick: int) -> tuple[int, int, int]:
        # Reuse GameState.date logic by temporarily snapshotting; cheap.
        from spqr.engine.world import (
            DAYS_PER_MONTH,
            HOURS_PER_DAY,
            MONTHS_PER_YEAR,
            START_YEAR_AUC,
        )
        total_days = tick // HOURS_PER_DAY
        year = START_YEAR_AUC + total_days // (DAYS_PER_MONTH * MONTHS_PER_YEAR)
        rem = total_days % (DAYS_PER_MONTH * MONTHS_PER_YEAR)
        month = rem // DAYS_PER_MONTH + 1
        day = rem % DAYS_PER_MONTH + 1
        return year, month, day
