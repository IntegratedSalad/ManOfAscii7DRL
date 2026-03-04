from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional, Literal

Color = Tuple[int, int, int]
ItemKind = Literal["ammo", "med"]

@dataclass
class Item: # TODO: change it to Crate class and add usable item
    x: int
    y: int
    kind: ItemKind

    ch: int
    fg: Color
    name: str

    amount: int  # ammo bullets or heal amount

    @staticmethod
    def ammo_crate(x: int, y: int, amount: int = 8) -> "Item":
        return Item(x=x, y=y, kind="ammo", ch=ord("A"), fg=(180, 180, 60), name="Ammo Crate", amount=amount)

    @staticmethod
    def med_crate(x: int, y: int, amount: int = 4) -> "Item":
        return Item(x=x, y=y, kind="med", ch=ord("+"), fg=(180, 80, 80), name="Medkit", amount=amount)
