"""Tests for the citizen flavor system — stochastic mood-driven log lines.

The flavor system is decorative: it reads district state and writes log
entries, but mutates nothing else. Tests verify the gate (only fires on
first-of-week), the mood→pool mapping (hungry conditions can produce a
hungry line; happy conditions don't produce a hungry line), the
no-mutation invariant, and engine-level determinism."""

from __future__ import annotations

import random

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.engine.world import HOURS_PER_MONTH, HOURS_PER_WEEK
from spqr.sim.systems import default_systems
from spqr.sim.systems import flavor


def _all_pool_lines() -> set[str]:
    """Union of every flavor pool — used to detect that *some* flavor
    line emitted, regardless of which mood category fired."""
    out: set[str] = set()
    for _, pool, _ in flavor._MOOD_TABLE:
        out.update(pool)
    return out


def test_no_emit_outside_first_of_week():
    """The week gate is the only thing that should let flavor.step run.
    With state.tick at non-week-boundary values the log must not grow."""
    state = new_game(seed=42, seed_starter=False)
    rng = random.Random(0)
    log_before = len(state.log)
    for tick in (1, 2, 17, 100, 167, HOURS_PER_WEEK + 1):
        state.tick = tick
        flavor.step(state, rng)
    assert len(state.log) == log_before


class _ForcedEmitRNG:
    """RNG wrapper whose first `random()` call returns 0.0 — guaranteed
    to pass the EMIT_PROBABILITY gate at the start of each district pass.
    Subsequent calls (the weighted-pick draw and randrange for line
    selection) delegate to a seeded Random so behavior is deterministic
    but still distributes across the mood pools."""

    def __init__(self, seed: int = 0):
        self._inner = random.Random(seed)
        self._gate_pending = True

    def random(self):
        if self._gate_pending:
            self._gate_pending = False
            return 0.0
        return self._inner.random()

    def randrange(self, n):
        return self._inner.randrange(n)

    def reset_gate(self) -> None:
        """Re-arm the forced-fire gate before the next district pass.
        flavor.step calls rng.random() once per district to test the
        EMIT_PROBABILITY gate, so this needs calling between
        flavor.step invocations to keep forcing the emit."""
        self._gate_pending = True


def test_first_of_week_can_emit():
    """At a first-of-week tick, with a controlled RNG that always passes
    the EMIT_PROBABILITY gate, exactly one entry is added per call."""
    state = new_game(seed=42, seed_starter=False)
    state.cities[0].districts[0].pops.plebs = 5.0  # so hungry weight > 0
    state.cities[0].treasury.grain = 0.0
    log_before = len(state.log)
    rng = _ForcedEmitRNG()
    state.tick = HOURS_PER_WEEK
    flavor.step(state, rng)
    assert len(state.log) == log_before + 1
    assert state.log[-1].text in _all_pool_lines()


def test_hungry_district_emits_hungry_line():
    """plebs > 0 + treasury.grain == 0 → hungry weight = 1.0; with no
    other negative-condition mood active, the weighted pick lands on
    hungry roughly 2/3 of the time (1.0 vs background 0.5). Force the
    EMIT_PROBABILITY gate to guarantee fires; over 12 forced weeks the
    chance of zero hungry lines is (0.5/1.5)^12 ≈ 1e-6."""
    state = new_game(seed=42, seed_starter=False)
    d = state.cities[0].districts[0]
    d.pops.plebs = 5.0
    d.pops.patricians = 0.0
    d.pops.unrest = 0.0
    d.satisfaction = 0.2
    state.cities[0].treasury.grain = 0.0
    rng = _ForcedEmitRNG(seed=123)
    for week in range(1, 13):
        state.tick = HOURS_PER_WEEK * week
        rng.reset_gate()
        flavor.step(state, rng)
    assert any(e.text in flavor.HUNGRY_LINES for e in state.log)


def test_content_district_does_not_emit_hungry_lines():
    """High satisfaction + full granary + plebs at low fraction of cap
    → hungry weight stays at 0. Over many weeks no HUNGRY_LINES entry
    can appear (the system never picks a mood with weight 0)."""
    state = new_game(seed=42, seed_starter=False)
    d = state.cities[0].districts[0]
    d.pops.plebs = 1.0
    d.satisfaction = 0.95
    state.cities[0].treasury.grain = 5_000.0
    rng = random.Random(456)
    for week in range(1, 25):
        state.tick = HOURS_PER_WEEK * week
        flavor.step(state, rng)
    assert not any(e.text in flavor.HUNGRY_LINES for e in state.log)


def test_does_not_mutate_state_outside_log():
    """Pure observer guarantee: flavor.step writes to state.log and
    NOTHING else. Snapshot every other field that could plausibly change
    and confirm equality after a step that's forced to emit."""
    state = new_game(seed=42, seed_starter=False)
    city = state.cities[0]
    d = city.districts[0]
    d.pops.plebs = 5.0
    city.treasury.grain = 0.0
    sat_before = d.satisfaction
    plebs_before = d.pops.plebs
    pats_before = d.pops.patricians
    unrest_before = d.pops.unrest
    grain_before = city.treasury.grain
    den_before = city.treasury.denarii
    timber_before = city.treasury.timber
    stone_before = city.treasury.stone
    n_buildings_before = len(city.buildings)
    state.tick = HOURS_PER_WEEK
    rng = random.Random(0)
    flavor.step(state, rng)
    assert d.satisfaction == sat_before
    assert d.pops.plebs == plebs_before
    assert d.pops.patricians == pats_before
    assert d.pops.unrest == unrest_before
    assert city.treasury.grain == grain_before
    assert city.treasury.denarii == den_before
    assert city.treasury.timber == timber_before
    assert city.treasury.stone == stone_before
    assert len(city.buildings) == n_buildings_before


def test_engine_determinism_across_runs():
    """Two engines from the same seed, stepped the same number of ticks,
    must produce the same state.log content (text, severity, tick).
    Catches any module-level random or clock leak in flavor."""
    def run():
        state = new_game(seed=42, seed_starter=False)
        # Seed a few plebs so non-trivial mood weights are non-zero
        # for several weeks; otherwise only background emits and the
        # test is too narrow.
        state.cities[0].districts[0].pops.plebs = 5.0
        eng = Engine(state, default_systems())
        eng.step(HOURS_PER_MONTH * 2)
        return [(e.tick, int(e.severity), e.text) for e in state.log]

    a = run()
    b = run()
    assert a == b


def test_no_harvest_log_lines_emitted():
    """Regression: the per-harvest log line was removed from grain.py.
    Run a city with a producing wheat farm for a full growing month and
    confirm no entry mentions a harvest."""
    from tests._helpers import bootstrap_starter_city

    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    bootstrap_starter_city(state, eng, plebs=10.0, grain_stocked=0.0)
    eng.step(HOURS_PER_MONTH * 2)
    assert not any("harvest" in e.text.lower() for e in state.log)
