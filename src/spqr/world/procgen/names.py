from __future__ import annotations

import random


CITY_FIRST = [
    "Nova", "Vetus", "Alba", "Aqua", "Castra", "Forum",
    "Colonia", "Vicus", "Mons",
]
CITY_SECOND = [
    "Augusta", "Iulia", "Aurelia", "Roma", "Flavia", "Traiana",
    "Veneta", "Domitia", "Lavinia",
]


def city_name(rng: random.Random) -> str:
    return f"{rng.choice(CITY_FIRST)} {rng.choice(CITY_SECOND)}"
