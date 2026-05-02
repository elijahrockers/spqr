"""Entry point for constructing a new GameState from a seed.

Lives at top level (not in `engine/`) because it depends on procgen, which
depends on models. Keeping it out of `engine/` avoids a cycle and lets the
engine package stay narrowly scoped to runtime concerns."""

from __future__ import annotations

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.rng import RngState, make_rng
from spqr.engine.world import GameState
from spqr.persistence.schema import SCHEMA_VERSION
from spqr.sim.models import NeighborSite, SiteKind
from spqr.world.procgen.region import generate_region
from spqr.world.procgen.city import generate_city


def new_game(seed: int) -> GameState:
    rng = make_rng(seed)
    province, (city_y, city_x) = generate_region(rng)
    city = generate_city(rng, region_x=city_x, region_y=city_y, city_id=0)

    # Register the city as a site on the province for region-view rendering.
    site_id = len(province.sites)
    province.sites.append(
        NeighborSite(
            id=site_id,
            name=city.name,
            kind=SiteKind.PLAYER_CITY,
            region_x=city_x,
            region_y=city_y,
        )
    )
    province.tiles[city_y * province.width + city_x].site_id = site_id

    state = GameState(
        schema_version=SCHEMA_VERSION,
        seed=seed,
        rng_state=RngState.capture(rng),
        province=province,
        cities=[city],
        player_city_id=0,
    )
    push_log(
        state.log,
        state.tick,
        LogSeverity.GOOD,
        f"{city.name} is founded. May Jupiter watch over the city.",
    )
    return state
