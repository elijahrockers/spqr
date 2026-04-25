from __future__ import annotations

import enum

import msgspec


class PopClass(enum.IntEnum):
    SLAVE = 0
    PLEB = 1
    EQUES = 2
    PATRICIAN = 3


class PopPool(msgspec.Struct, frozen=False):
    """Aggregate population counts. Fractional counts are tolerated between
    monthly demographic resolutions; integer rounding happens on report."""

    slaves: float = 0.0
    plebs: float = 0.0
    equites: float = 0.0
    patricians: float = 0.0
    unrest: float = 0.0  # 0.0 calm .. 1.0 revolt

    def total(self) -> float:
        return self.slaves + self.plebs + self.equites + self.patricians

    def workers(self) -> float:
        # Slaves and plebs supply labor; equites/patricians do not till fields.
        return self.slaves + self.plebs

    def soldiers_eligible(self) -> float:
        # Plebs are the legionary base in the early Republic abstraction.
        return self.plebs * 0.4
