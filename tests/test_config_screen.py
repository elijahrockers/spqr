"""Tests for the (c)onfigure modal — building configuration dialog.

Today the only kind with anything to configure is FARM (crop selection).
Other kinds open a "nothing to configure" placeholder."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.sim.models import BuildingKind, Crop
from spqr.sim.systems import default_systems
from spqr.ui.screens.config import (
    CROP_SWITCH_CONFIRM_THRESHOLD,
    ConfigResult,
    ConfigScreen,
    _render_farm_config,
    _render_no_config,
)

from ._helpers import bootstrap_starter_city


def test_config_result_close_carries_no_payload():
    r = ConfigResult(kind="close")
    assert r.farm_id is None
    assert r.crop is None


def test_set_crop_result_carries_farm_and_crop():
    r = ConfigResult(kind="set_crop", farm_id=7, crop=Crop.VEGETABLES)
    assert r.farm_id == 7
    assert r.crop == Crop.VEGETABLES


def test_render_farm_config_shows_current_crop_and_options():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = 0.10  # below threshold
    text = str(_render_farm_config(farm, pending=None))
    assert "CONFIGURE FARM" in text
    assert "wheat" in text
    assert "vegetables" in text
    # Both hotkeys should be visible.
    assert "1" in text
    assert "2" in text


def test_render_farm_config_shows_pending_confirmation():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = 0.50  # above threshold
    text = str(_render_farm_config(farm, pending=Crop.VEGETABLES))
    assert "Switching to" in text
    assert "vegetables" in text
    assert "discard" in text or "Discard" in text
    assert "Y" in text
    assert "N" in text


def test_render_no_config_for_non_farm():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    granary = handles["granary"]
    text = str(_render_no_config(granary))
    assert "CONFIGURE" in text
    assert "Nothing to configure" in text


def test_pick_crop_low_maturity_dismisses_immediately():
    """Below CROP_SWITCH_CONFIRM_THRESHOLD, the farm crop change goes
    through without confirmation."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = CROP_SWITCH_CONFIRM_THRESHOLD - 0.01

    screen = ConfigScreen(state, farm.id)
    # Stub out dismiss to capture the result.
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_crop("1")  # vegetables

    assert len(captured) == 1
    assert captured[0].kind == "set_crop"
    assert captured[0].farm_id == farm.id
    assert captured[0].crop == Crop.VEGETABLES
    # Pending should not be set since no confirmation needed.
    assert screen._pending_crop is None


def test_pick_crop_high_maturity_requires_confirmation():
    """Above the threshold, the modal stashes the request and waits for y/n."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = CROP_SWITCH_CONFIRM_THRESHOLD + 0.05

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    # Selecting a different crop should not dismiss yet.
    screen.action_pick_crop("1")
    assert len(captured) == 0
    assert screen._pending_crop == Crop.VEGETABLES

    # Confirm with y -> dismiss with set_crop.
    screen.action_confirm()
    assert len(captured) == 1
    assert captured[0].kind == "set_crop"
    assert captured[0].crop == Crop.VEGETABLES


def test_pick_crop_high_maturity_can_be_cancelled():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = 0.60

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_crop("1")  # request vegetables, get pending
    assert screen._pending_crop == Crop.VEGETABLES
    screen.action_cancel_pending()
    # Cancel just clears pending; does not dismiss.
    assert len(captured) == 0
    assert screen._pending_crop is None


def test_picking_same_crop_closes_silently():
    """Picking the crop that's already sown is a no-op — close, don't
    submit a redundant SetFarmCrop."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.WHEAT)
    farm.grain_maturity = 0.80  # well above threshold

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_crop("0")  # wheat (current)
    assert len(captured) == 1
    assert captured[0].kind == "close"
    assert screen._pending_crop is None


def test_close_action_dismisses_with_close():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_close()
    assert len(captured) == 1
    assert captured[0].kind == "close"
