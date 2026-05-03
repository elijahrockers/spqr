"""Default system registration. The order matters:
  - labor allocates workforce to builder slots (under construction) and
    worker slots (operational) before any consumer of `workers_assigned`
  - construction reads workers_assigned to advance completion
  - grain reads workers_assigned to grow crops on farms; runs the harvest,
    transport-to-granary, and per-house consumption pipeline; finally
    syncs treasury.grain as the granary aggregate
  - industry reads workers_assigned on lumber mills + quarries to
    produce timber/stone into the treasury, halted at storage cap
  - housing runs monthly: residences with a road in reach and the
    required materials (timber + stone for cottages/insulae) in the
    treasury advance one tier. Must precede population so the same
    month sees the bumped capacity.
  - economy runs monthly: taxation and dole — drains the granaries via
    grain.drain_treasury_grain
  - demographics runs last so it observes post-economy state."""

from . import construction, economy, grain, housing, industry, labor, population
from spqr.engine.tick import System


def default_systems() -> list[System]:
    return [
        labor.step,
        construction.step,
        grain.step,
        industry.step,
        housing.step,
        economy.step,
        population.step,
    ]


__all__ = ["default_systems"]
