from __future__ import annotations

import msgspec


class Resources(msgspec.Struct, frozen=False):
    grain: float = 0.0
    denarii: float = 0.0
    timber: float = 0.0
    stone: float = 0.0

    def add(self, other: "Resources") -> None:
        self.grain += other.grain
        self.denarii += other.denarii
        self.timber += other.timber
        self.stone += other.stone

    def can_pay(self, cost: "Resources") -> bool:
        return (
            self.grain >= cost.grain
            and self.denarii >= cost.denarii
            and self.timber >= cost.timber
            and self.stone >= cost.stone
        )

    def pay(self, cost: "Resources") -> None:
        self.grain -= cost.grain
        self.denarii -= cost.denarii
        self.timber -= cost.timber
        self.stone -= cost.stone
