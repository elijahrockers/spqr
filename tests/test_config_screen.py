"""Tests for the (c)onfigure modal — building configuration dialog.

Covers FARM (crop selection with maturity confirmation), RESIDENCE
(tier-cap selection), and the no-config placeholder for other kinds.
Also pins the no-Rich-markup-leak invariant: rendered Text must not
contain the literal `[dim]` / `[bright_yellow]` substrings — those mean
markup leaked into output instead of being interpreted."""

from __future__ import annotations

from spqr.bootstrap import new_game
from spqr.engine.commands import PlaceZone, ZoneKind
from spqr.engine.tick import Engine
from spqr.sim.models import (
    RESIDENCE_MAX_TIER,
    BuildingKind,
    Crop,
)
from spqr.sim.systems import default_systems
from spqr.ui.screens.config import (
    CROP_SWITCH_CONFIRM_THRESHOLD,
    ConfigResult,
    ConfigScreen,
    _render_farm_config,
    _render_no_config,
    _render_residence_config,
)

from ._helpers import bootstrap_starter_city, find_clear_grass


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
    # Both hotkeys should be visible — char hotkeys w/v.
    assert "w" in text
    assert "v" in text


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


# --- Rich markup leak guard -------------------------------------------------

# The bug we're guarding against: text.append("...[dim]close[/]...")
# treats the brackets as literal characters rather than parsing them as
# markup. Players see `[dim]escape / c to close[/]` rendered verbatim.
# The fix is style= kwargs or split appends; these tests pin it.

def _assert_no_markup_leaks(rendered: str) -> None:
    for needle in ("[dim]", "[/]", "[bright_yellow]", "[bright_green]", "[bold]"):
        assert needle not in rendered, (
            f"Rich markup literal leaked into output: {needle!r}\n{rendered}"
        )


def test_farm_config_does_not_leak_markup():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.grain_maturity = 0.10
    _assert_no_markup_leaks(str(_render_farm_config(farm, pending=None)))
    farm.grain_maturity = 0.50
    _assert_no_markup_leaks(
        str(_render_farm_config(farm, pending=Crop.VEGETABLES))
    )


def test_residence_config_does_not_leak_markup():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]
    _assert_no_markup_leaks(str(_render_residence_config(house)))


def test_no_config_does_not_leak_markup():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    _assert_no_markup_leaks(str(_render_no_config(handles["granary"])))


# --- Residence tier-cap config ---------------------------------------------

def test_render_residence_config_lists_all_tiers():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]
    text = str(_render_residence_config(house))
    assert "CONFIGURE RESIDENCE" in text
    # All four tier names should appear as picker options.
    for name in ("undeveloped", "huts", "cottages", "insula"):
        assert name in text
    # Default cap is RESIDENCE_MAX_TIER = uncapped.
    assert "uncapped" in text or "none" in text


def test_pick_tier_cap_dismisses_with_set_tier_cap():
    """Selecting a tier on a residence dismisses with kind=set_tier_cap
    and the new cap. Tests drive `action_pick_char` directly since
    that's what the keybindings invoke. Hotkeys: u/h/o/i for
    undeveloped/huts/cottages/insula."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]
    assert house.tier_cap == RESIDENCE_MAX_TIER  # default

    screen = ConfigScreen(state, house.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("h")  # cap at huts
    assert len(captured) == 1
    assert captured[0].kind == "set_tier_cap"
    assert captured[0].building_id == house.id
    assert captured[0].tier_cap == 1


def test_pick_same_tier_cap_closes_silently():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]
    house.tier_cap = 2

    screen = ConfigScreen(state, house.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("o")  # cottages = current cap
    assert len(captured) == 1
    assert captured[0].kind == "close"


def test_residence_dispatcher_ignores_unknown_keys():
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    house = handles["house"]

    screen = ConfigScreen(state, house.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    # 'w' is a farm crop key, not a tier-cap key — should be a no-op
    # on a residence.
    screen.action_pick_char("w")
    assert len(captured) == 0


def test_farm_dispatcher_ignores_unknown_keys():
    """A residence's tier-cap key (`u`/`h`/`o`/`i`) must not pick a
    crop on a focused farm."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("h")  # tier-cap key, irrelevant on farm
    assert len(captured) == 0
    screen.action_pick_char("o")  # also irrelevant
    assert len(captured) == 0


def test_pick_char_w_picks_wheat_on_farm():
    """The new char hotkey path for crops: `w` = wheat, `v` = vegetables."""
    state = new_game(seed=42, seed_starter=False)
    eng = Engine(state, default_systems())
    handles = bootstrap_starter_city(state, eng)
    farm = handles["farm"]
    farm.crop = int(Crop.VEGETABLES)
    farm.grain_maturity = 0.0

    screen = ConfigScreen(state, farm.id)
    captured: list[ConfigResult] = []
    screen.dismiss = lambda r: captured.append(r)  # type: ignore[assignment]
    screen.action_pick_char("w")
    assert len(captured) == 1
    assert captured[0].kind == "set_crop"
    assert captured[0].crop == Crop.WHEAT
