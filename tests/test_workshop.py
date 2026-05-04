"""Tests for the workshop's good selection and material-conversion
production loop. Furniture consumes timber; stoneware consumes stone.
Production halts when input is exhausted — no partial yields."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, SetWorkshopGood, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    BuildingKind,
    Good,
    WORKSHOP_INPUT_PER_WORKER_PER_TICK,
    WORKSHOP_OUTPUT_PER_WORKER_PER_TICK,
)
from spqr.sim.systems import default_systems
from spqr.ui.screens.config import (
    ConfigResult,
    ConfigScreen,
    _render_workshop_config,
)

from ._helpers import find_clear_grass


def _operational_workshop(seed=42, plebs=50.0):
    state = new_game(seed=seed, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    city.treasury.timber = 1000.0
    city.treasury.stone = 1000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.WORKSHOP))
    eng.step(1)
    ws = next(b for b in city.buildings if b.kind == BuildingKind.WORKSHOP)
    ws.completion = 1.0
    city.districts[0].pops.plebs = plebs
    return state, eng, city, ws


# --- Good selection ---------------------------------------------------------

def test_new_workshop_defaults_to_furniture():
    state, _eng, _city, ws = _operational_workshop()
    assert ws.good == int(Good.FURNITURE)


def test_set_workshop_good_command_switches_good():
    state, eng, _city, ws = _operational_workshop()
    eng.submit(SetWorkshopGood(building_id=ws.id, good=int(Good.STONEWARE)))
    eng.step(1)
    assert ws.good == int(Good.STONEWARE)


def test_set_workshop_good_ignored_for_non_workshop():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    city = state.player_city()
    city.treasury.denarii = 10_000.0
    spot = find_clear_grass(city)
    eng.submit(PlaceZone(x=spot[0], y=spot[1], kind=ZoneKind.GRANARY))
    eng.step(1)
    granary = next(b for b in city.buildings if b.kind == BuildingKind.GRANARY)
    granary.good = 0  # baseline
    eng.submit(SetWorkshopGood(building_id=granary.id, good=int(Good.STONEWARE)))
    eng.step(1)
    assert granary.good == 0  # no-op for non-workshop


# --- Production -------------------------------------------------------------

def test_furniture_workshop_consumes_timber_and_produces_furniture():
    state, eng, city, ws = _operational_workshop()
    ws.good = int(Good.FURNITURE)
    eng.step(1)  # labor.step assigns workers
    assert ws.workers_assigned > 0
    timber_before = city.treasury.timber
    furniture_before = city.treasury.furniture
    eng.step(50)
    expected_in = (
        WORKSHOP_INPUT_PER_WORKER_PER_TICK * ws.workers_assigned * 50
    )
    expected_out = (
        WORKSHOP_OUTPUT_PER_WORKER_PER_TICK * ws.workers_assigned * 50
    )
    # Use float-tolerant comparison: 50 cumulative additions of a
    # non-binary-exact constant (0.03 × workers) accumulate FP noise.
    assert abs((timber_before - city.treasury.timber) - expected_in) < 1e-9
    assert abs((city.treasury.furniture - furniture_before) - expected_out) < 1e-9


def test_stoneware_workshop_consumes_stone_and_produces_stoneware():
    state, eng, city, ws = _operational_workshop()
    ws.good = int(Good.STONEWARE)
    eng.step(1)
    stone_before = city.treasury.stone
    stoneware_before = city.treasury.stoneware
    eng.step(50)
    expected_in = (
        WORKSHOP_INPUT_PER_WORKER_PER_TICK * ws.workers_assigned * 50
    )
    expected_out = (
        WORKSHOP_OUTPUT_PER_WORKER_PER_TICK * ws.workers_assigned * 50
    )
    assert abs((stone_before - city.treasury.stone) - expected_in) < 1e-9
    assert abs((city.treasury.stoneware - stoneware_before) - expected_out) < 1e-9


def test_workshop_halts_when_input_runs_out():
    """No partial yields. When the treasury can't cover one tick of
    consumption, the workshop produces nothing for that tick."""
    state, eng, city, ws = _operational_workshop()
    ws.good = int(Good.FURNITURE)
    eng.step(1)
    # Exhaust timber so any production attempt fails. Leave just
    # enough for ~one tick.
    one_tick = WORKSHOP_INPUT_PER_WORKER_PER_TICK * ws.workers_assigned
    city.treasury.timber = one_tick - 0.001  # not enough
    furniture_before = city.treasury.furniture
    eng.step(20)
    # No production at all — input was always insufficient.
    assert city.treasury.furniture == furniture_before


# --- ConfigScreen -----------------------------------------------------------

def test_render_workshop_config_lists_both_goods():
    state, _eng, _city, ws = _operational_workshop()
    text = str(_render_workshop_config(ws))
    assert "CONFIGURE WORKSHOP" in text
    assert "furniture" in text
    assert "stoneware" in text
    assert "consumes timber" in text
    assert "consumes stone" in text


def test_pick_char_f_picks_furniture_on_workshop():
    state, _eng, _city, ws = _operational_workshop()
    ws.good = int(Good.STONEWARE)  # start as stoneware so f flips it

    screen = ConfigScreen(state, ws.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("f")
    assert len(captured) == 1
    assert captured[0].kind == "set_good"
    assert captured[0].building_id == ws.id
    assert captured[0].good == Good.FURNITURE


def test_pick_char_s_picks_stoneware_on_workshop():
    state, _eng, _city, ws = _operational_workshop()
    ws.good = int(Good.FURNITURE)  # default

    screen = ConfigScreen(state, ws.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("s")
    assert len(captured) == 1
    assert captured[0].kind == "set_good"
    assert captured[0].good == Good.STONEWARE


def test_picking_same_good_closes_silently():
    state, _eng, _city, ws = _operational_workshop()
    ws.good = int(Good.FURNITURE)

    screen = ConfigScreen(state, ws.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("f")  # already furniture
    assert len(captured) == 1
    assert captured[0].kind == "close"
