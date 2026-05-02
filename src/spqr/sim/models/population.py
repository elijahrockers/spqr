from __future__ import annotations

import enum

import msgspec


class PopClass(enum.IntEnum):
    PLEB = 0
    PATRICIAN = 1


class PopPool(msgspec.Struct, frozen=False):
    """Aggregate population counts. Fractional counts are tolerated between
    monthly demographic resolutions; integer rounding happens on report."""

    plebs: float = 0.0
    patricians: float = 0.0
    unrest: float = 0.0  # 0.0 calm .. 1.0 revolt

    def total(self) -> float:
        return self.plebs + self.patricians

    def workers(self) -> float:
        # Plebs supply labor; patricians do not till fields.
        return self.plebs
