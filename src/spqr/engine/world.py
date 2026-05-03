from __future__ import annotations

import enum
import random

import msgspec

from spqr.sim.models import City, Province

from .events import LogEntry
from .rng import RngState, make_rng


class Speed(enum.IntEnum):
    PAUSED = 0
    NORMAL = 1
    FAST = 2
    FASTER = 3
    FASTEST = 4


# Real-time tick rate per speed setting.
SPEED_TICKS_PER_SEC: dict[Speed, int] = {
    Speed.PAUSED: 0,
    Speed.NORMAL: 1,
    Speed.FAST: 4,
    Speed.FASTER: 16,
    Speed.FASTEST: 64,
}


# Hours per game day / month / year. We use a simplified Roman calendar:
# 30-day months, 12 months/year — close enough for sim purposes.
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
HOURS_PER_WEEK = HOURS_PER_DAY * DAYS_PER_WEEK
HOURS_PER_MONTH = HOURS_PER_DAY * DAYS_PER_MONTH
HOURS_PER_YEAR = HOURS_PER_MONTH * MONTHS_PER_YEAR

# Starting in-game year (AUC = ab urbe condita; 753 BC ~ year 1).
START_YEAR_AUC = 500
# Starting month, 1..12. Tick 0 maps to day 1 of this month so the
# player begins the game at the start of the growing season instead of
# the middle of winter.
START_MONTH = 3


class GameState(msgspec.Struct, frozen=False):
    """Root of all serialized game state.

    Anything mutated during simulation must live somewhere on this tree.
    Off-tree state (in-memory caches, the live Random instance) is recreated
    from this struct at load time."""

    schema_version: int
    seed: int
    rng_state: RngState
    province: Province
    cities: list[City]
    player_city_id: int
    tick: int = 0
    speed: Speed = Speed.NORMAL
    log: list[LogEntry] = msgspec.field(default_factory=list)

    def player_city(self) -> City:
        return self.cities[self.player_city_id]

    def date(self) -> tuple[int, int, int]:
        """Return (year_auc, month_1_to_12, day_1_to_30). Tick 0 maps to
        month=START_MONTH so the player begins in spring rather than
        winter; the offset wraps around year boundaries naturally."""
        total_days = self.tick // HOURS_PER_DAY
        shifted = total_days + (START_MONTH - 1) * DAYS_PER_MONTH
        year = START_YEAR_AUC + int(shifted // (DAYS_PER_MONTH * MONTHS_PER_YEAR))
        rem = shifted % (DAYS_PER_MONTH * MONTHS_PER_YEAR)
        month = int(rem // DAYS_PER_MONTH) + 1
        day = int(rem % DAYS_PER_MONTH) + 1
        return year, month, day

    def hour(self) -> int:
        return self.tick % HOURS_PER_DAY


def restore_rng(state: GameState) -> random.Random:
    """Reconstruct the live RNG from the serialized state. The caller is
    responsible for capturing the RNG back into state before saving."""
    if state.rng_state.state:
        return state.rng_state.restore()
    return make_rng(state.seed)
