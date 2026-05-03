"""Tests for the inspector's per-residence occupancy display.

Pops are tracked at the district level; the inspector derives a
per-residence count for display. The allocation must sum across all
residences in a district to exactly the rounded district pop, otherwise
the inspector reports more (or fewer) plebs than the status bar."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import BuildingKind
from spqr.sim.systems import default_systems
from spqr.ui.widgets.inspector import _residence_occupancy


def _three_residences():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    for i in range(3):
        eng.submit(PlaceZone(x=10 + i, y=10, kind=ZoneKind.RESIDENCE))
    eng.step(1)
    residences = [b for b in city.buildings if b.kind == BuildingKind.RESIDENCE]
    assert len(residences) == 3
    return city, residences


def test_per_residence_occupancy_sums_to_rounded_district_pop():
    """The original bug: 5 plebs across 3 tier-0 residences (cap 3 each)
    rendered as 2/3 in each, summing to 6 — one more than the status
    bar's 5. Allocation must sum to round(district.pops.plebs)."""
    city, residences = _three_residences()
    city.districts[0].pops.plebs = 5.0
    occs = [_residence_occupancy(city, r) for r in residences]
    assert sum(occs) == 5
    # And every per-residence value is within capacity.
    for r, occ in zip(residences, occs):
        assert 0 <= occ <= r.residence_capacity()


def test_per_residence_occupancy_rounds_with_status_bar():
    """7.5 plebs: status bar `:.0f` rounds to 8 (banker's rounding rounds
    half to even, so 7.5 → 8). Per-residence sum must match."""
    city, residences = _three_residences()
    city.districts[0].pops.plebs = 7.5
    occs = [_residence_occupancy(city, r) for r in residences]
    assert sum(occs) == round(7.5)


def test_full_district_assigns_capacity_to_every_residence():
    """At capacity (9 plebs / 9 cap), every residence should be exactly
    full so all three render bright_green."""
    city, residences = _three_residences()
    city.districts[0].pops.plebs = 9.0
    occs = [_residence_occupancy(city, r) for r in residences]
    assert occs == [3, 3, 3]
    for r, occ in zip(residences, occs):
        assert occ == r.residence_capacity()


def test_empty_district_returns_zero_for_each_residence():
    city, residences = _three_residences()
    city.districts[0].pops.plebs = 0.0
    occs = [_residence_occupancy(city, r) for r in residences]
    assert occs == [0, 0, 0]


def test_allocation_is_stable_across_calls():
    """With identical state, two consecutive queries must return the
    same per-residence allocation — required for deterministic display."""
    city, residences = _three_residences()
    city.districts[0].pops.plebs = 5.0
    a = [_residence_occupancy(city, r) for r in residences]
    b = [_residence_occupancy(city, r) for r in residences]
    assert a == b
