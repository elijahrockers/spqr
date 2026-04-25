from __future__ import annotations

import enum

import msgspec


class LogSeverity(enum.IntEnum):
    INFO = 0
    GOOD = 1
    WARNING = 2
    BAD = 3


class LogEntry(msgspec.Struct, frozen=False):
    """A single line in the rolling event log."""
    tick: int
    severity: LogSeverity
    text: str


# Maximum entries retained on GameState.log; older entries are evicted on push.
LOG_MAX = 200


def push_log(log: list[LogEntry], tick: int, severity: LogSeverity, text: str) -> None:
    log.append(LogEntry(tick=tick, severity=severity, text=text))
    if len(log) > LOG_MAX:
        del log[: len(log) - LOG_MAX]
