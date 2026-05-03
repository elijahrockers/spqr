from __future__ import annotations

import msgspec


class Resources(msgspec.Struct, frozen=False):
    grain: float = 0.0
    denarii: float = 0.0
    timber: float = 0.0
    stone: float = 0.0
    vegetables: float = 0.0
    # Workshop output goods. Furniture is produced from timber;
    # stoneware from stone. Stored as treasury aggregates with no
    # consumer in MVP — they're a visible signal that workshops are
    # converting raw materials into finished goods.
    furniture: float = 0.0
    stoneware: float = 0.0

    def add(self, other: "Resources") -> None:
        self.grain += other.grain
        self.denarii += other.denarii
        self.timber += other.timber
        self.stone += other.stone
        self.vegetables += other.vegetables
        self.furniture += other.furniture
        self.stoneware += other.stoneware

    def can_pay(self, cost: "Resources") -> bool:
        return (
            self.grain >= cost.grain
            and self.denarii >= cost.denarii
            and self.timber >= cost.timber
            and self.stone >= cost.stone
            and self.vegetables >= cost.vegetables
            and self.furniture >= cost.furniture
            and self.stoneware >= cost.stoneware
        )

    def pay(self, cost: "Resources") -> None:
        self.grain -= cost.grain
        self.denarii -= cost.denarii
        self.timber -= cost.timber
        self.stone -= cost.stone
        self.vegetables -= cost.vegetables
        self.furniture -= cost.furniture
        self.stoneware -= cost.stoneware
