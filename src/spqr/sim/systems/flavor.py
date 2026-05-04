"""Citizen flavor — stochastic mood-driven log lines reflecting living
conditions in each district. Decorative only: reads state, writes log,
mutates nothing else. Runs weekly per district with a 50% gate so the
annals stay sparse (~2 lines per game month per district).

Mood weights are recomputed from current state each week — there's no
cached signal. The weighted pick falls back to a "background" pool that
is always available, so a calm city still occasionally murmurs."""

from __future__ import annotations

import random

from spqr.engine.events import LogSeverity, push_log
from spqr.engine.world import GameState, is_first_of_week
from spqr.sim.models import BuildingKind, City, District

from .housing import _industrial_nuisance_tiles


# Per-district per-week probability of emitting any flavor line.
# At 0.05, ~1 line every 5 game months per district — flavor stays
# rare enough to feel noteworthy when it appears.
EMIT_PROBABILITY: float = 0.05

# Satisfaction floor below which the "content" mood weight is zero —
# only happy districts boast.
CONTENT_THRESHOLD: float = 0.7

# Always-available baseline so even a calm district has something to say.
BACKGROUND_BASELINE: float = 0.5


HUNGRY_LINES: tuple[str, ...] = (
    "A baker shutters his stall — no grain to bake.",
    "Children cry in the alleys; mothers have no bread to give.",
    "A laborer pawns his cloak for a single loaf.",
    "Beggars crowd the temple steps where once they did not.",
    "An old woman is found at her door, her cupboard bare.",
    "Rumors spread of grain hoarders in the warehouses.",
)

RESTLESS_LINES: tuple[str, ...] = (
    "Graffiti against the duumviri appears on the forum wall.",
    "A drunken soldier curses the magistrates and goes unpunished.",
    "Crowds gather in the streets, then scatter when the lictors pass.",
    "A petty theft becomes a street brawl before nightfall.",
    "Voices in the wineshop grow louder as the news from Rome is read.",
    "An effigy of the praetor is burned outside the basilica.",
)

NUISANCE_LINES: tuple[str, ...] = (
    "A weaver complains of soot on her morning laundry.",
    "The smithy's hammer wakes the children before dawn again.",
    "Quarrymen track white dust into every shop on the lane.",
    "An insula tenant pleads with the aedile about the smell.",
    "Mortar by the kiln runs gray when it rains.",
    "Neighbors petition the duumviri to move the lumberyard.",
)

CROWDED_LINES: tuple[str, ...] = (
    "A new family sleeps under the colonnade for want of a roof.",
    "Three brothers and their wives crowd a single cubiculum.",
    "The tabernae upstairs are subdivided to fit a sixth tenant.",
    "A landlord raises rents on the insula by another sestertius.",
    "Strangers share beds by shifts in the cheaper boarding houses.",
    "The fountain runs dry by midmorning from the press of buckets.",
)

IDLE_LINES: tuple[str, ...] = (
    "Day-laborers loiter near the forum, hoping for hire.",
    "A young man dices away the morning he meant to spend at work.",
    "Stevedores nap on the warehouse steps; no carts have come today.",
    "A mason sharpens his chisels for the third time, waiting.",
    "Workers gather at the crossroads gossiping, with no one to call them.",
    "A freedman walks the basilica all day looking for a patron.",
)

CONTENT_LINES: tuple[str, ...] = (
    "A wedding feast spills into the street; neighbors join the music.",
    "Children play knucklebones in the warm dust of the forum.",
    "A baker gives away yesterday's loaves to passersby.",
    "Old men trade jokes on the temple steps, well-fed and unhurried.",
    "A fishwife sings as she scales the morning's catch.",
    "The wine at the corner taberna is good and the company better.",
)

PATRICIAN_LINES: tuple[str, ...] = (
    "A senator boasts of his new mosaic at supper.",
    "A matron parades a fresh stola through the forum, all eyes following.",
    "A patrician's litter passes, perfumed with rose and sandalwood.",
    "A young equestrian commissions a marble bust of his father.",
    "A noblewoman hosts poets at her domus and complains they are dull.",
    "A patrician boy receives his toga virilis to applause.",
)

BACKGROUND_LINES: tuple[str, ...] = (
    "A fishmonger calls his wares from the market steps.",
    "A scribe sets up his stool to write letters for a copper or two.",
    "An augur peers at the entrails of a dove and pronounces the day fair.",
    "Wagons rumble through the gate at dawn, bound for the country.",
    "A barber gossips with his customer about chariot odds at the circus.",
    "A stray dog steals a sausage and is chased through the lane.",
)


# (mood_key, pool, severity). Iteration order is stable across runs and
# affects determinism of _weighted_pick, so keep this tuple-of-tuples
# rather than a dict literal.
_MOOD_TABLE: tuple[tuple[str, tuple[str, ...], LogSeverity], ...] = (
    ("hungry",     HUNGRY_LINES,     LogSeverity.BAD),
    ("restless",   RESTLESS_LINES,   LogSeverity.BAD),
    ("nuisance",   NUISANCE_LINES,   LogSeverity.BAD),
    ("crowded",    CROWDED_LINES,    LogSeverity.INFO),
    ("idle",       IDLE_LINES,       LogSeverity.INFO),
    ("content",    CONTENT_LINES,    LogSeverity.GOOD),
    ("patrician",  PATRICIAN_LINES,  LogSeverity.GOOD),
    ("background", BACKGROUND_LINES, LogSeverity.INFO),
)

_POOL_BY_MOOD: dict[str, tuple[tuple[str, ...], LogSeverity]] = {
    key: (pool, severity) for key, pool, severity in _MOOD_TABLE
}


def step(state: GameState, rng: random.Random) -> None:
    if not is_first_of_week(state.tick):
        return
    for city in state.cities:
        for d in city.districts:
            if rng.random() >= EMIT_PROBABILITY:
                continue
            weights = _mood_weights(city, d)
            mood = _weighted_pick(weights, rng)
            if mood is None:
                continue
            pool, severity = _POOL_BY_MOOD[mood]
            line = pool[rng.randrange(len(pool))]
            push_log(state.log, state.tick, severity, line)


def _mood_weights(city: City, d: District) -> dict[str, float]:
    return {
        "hungry":     _hungry_weight(city, d),
        "restless":   _restless_weight(d),
        "nuisance":   _nuisance_weight(city, d),
        "crowded":    _crowded_weight(city, d),
        "idle":       _idle_weight(city, d),
        "content":    _content_weight(d),
        "patrician":  _patrician_weight(d),
        "background": BACKGROUND_BASELINE,
    }


def _weighted_pick(weights: dict[str, float], rng: random.Random) -> str | None:
    total = sum(w for w in weights.values() if w > 0.0)
    if total <= 0.0:
        return None
    draw = rng.random() * total
    cumulative = 0.0
    for key, w in weights.items():
        if w <= 0.0:
            continue
        cumulative += w
        if draw < cumulative:
            return key
    # Floating-point edge case: draw == total. Return the last positive key.
    for key in reversed(list(weights.keys())):
        if weights[key] > 0.0:
            return key
    return None


def _hungry_weight(city: City, d: District) -> float:
    if d.pops.plebs <= 0.0:
        return 0.0
    if city.treasury.grain > 0.0:
        return 0.0
    return 1.0


def _restless_weight(d: District) -> float:
    return max(0.0, min(1.0, d.pops.unrest))


def _nuisance_weight(city: City, d: District) -> float:
    nuisance_tiles = _industrial_nuisance_tiles(city)
    if not nuisance_tiles:
        return 0.0
    residences = [
        city.buildings[b_id]
        for b_id in d.building_ids
        if city.buildings[b_id].kind == BuildingKind.RESIDENCE
        and city.buildings[b_id].is_completed
    ]
    if not residences:
        return 0.0
    affected = sum(1 for r in residences if (r.x, r.y) in nuisance_tiles)
    return affected / len(residences)


def _crowded_weight(city: City, d: District) -> float:
    cap = sum(
        city.buildings[b_id].residence_capacity()
        for b_id in d.building_ids
        if city.buildings[b_id].kind == BuildingKind.RESIDENCE
        and city.buildings[b_id].is_completed
    )
    if cap <= 0:
        return 0.0
    return max(0.0, min(1.0, d.pops.plebs / cap))


def _idle_weight(city: City, d: District) -> float:
    workers = d.pops.workers()
    if workers <= 0:
        return 0.0
    assigned = sum(
        city.buildings[b_id].workers_assigned for b_id in d.building_ids
    )
    leftover = max(0.0, workers - assigned)
    return min(1.0, leftover / workers)


def _content_weight(d: District) -> float:
    return max(0.0, d.satisfaction - CONTENT_THRESHOLD)


def _patrician_weight(d: District) -> float:
    pat_factor = min(1.0, d.pops.patricians / 10.0)
    return pat_factor * max(0.0, min(1.0, d.satisfaction))
