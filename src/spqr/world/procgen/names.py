from __future__ import annotations

import random

PRAENOMINA = [
    "Marcus", "Lucius", "Gaius", "Quintus", "Titus", "Publius",
    "Aulus", "Gnaeus", "Decimus", "Servius", "Tiberius",
]

NOMINA = [
    "Iulius", "Cornelius", "Claudius", "Aemilius", "Fabius",
    "Valerius", "Sempronius", "Licinius", "Calpurnius", "Marcius",
    "Tullius", "Postumius", "Sulpicius", "Manlius",
]

COGNOMINA = [
    "Maximus", "Brutus", "Severus", "Cato", "Cicero", "Magnus",
    "Felix", "Pius", "Rufus", "Niger", "Albus", "Crispus",
    "Longus", "Caesar", "Scipio", "Lepidus",
]


CITY_FIRST = [
    "Nova", "Vetus", "Alba", "Aqua", "Castra", "Forum",
    "Colonia", "Vicus", "Mons",
]
CITY_SECOND = [
    "Augusta", "Iulia", "Aurelia", "Roma", "Flavia", "Traiana",
    "Veneta", "Domitia", "Lavinia",
]

BARBARIAN_TRIBES = [
    "Gauls", "Germani", "Iberii", "Britons", "Dacians", "Sarmatians",
    "Carpi", "Vandilii", "Marcomanni",
]


def roman_name(rng: random.Random) -> str:
    return f"{rng.choice(PRAENOMINA)} {rng.choice(NOMINA)} {rng.choice(COGNOMINA)}"


def city_name(rng: random.Random) -> str:
    return f"{rng.choice(CITY_FIRST)} {rng.choice(CITY_SECOND)}"


def barbarian_camp_name(rng: random.Random) -> str:
    return f"Camp of the {rng.choice(BARBARIAN_TRIBES)}"
