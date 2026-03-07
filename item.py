from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional, Literal, Protocol

Color = Tuple[int, int, int]
CrateKind = Literal["ammo", "med"]

@dataclass
class WeaponData: # move it to the item.py, as weapons will drop upon death, and can be picked up by other actors.
    name: str
    range: int
    base_accuracy: int  # percent
    damage: int
    mag_size: int

RIFLE = WeaponData("Rifle", range=12, base_accuracy=70, damage=3, mag_size=6)
SMG = WeaponData("SMG", range=8, base_accuracy=65, damage=2, mag_size=10)
SNIPER = WeaponData("Sniper", range=16, base_accuracy=80, damage=4, mag_size=4)

class UseContext(Protocol):
    game_map: object

    def log_add(self, msg: str) -> None: ...
    def spawn_explostion(self, x: int, y: int, radius: int, damage: int, source_team: int, spawns_shrapnel: bool) -> None: ...

@dataclass
class Item:
    name: str
    ch: int
    fg: Color
    stackable: bool = False
    qty: int = 1

    x: Optional[int] = None
    y: Optional[int] = None

    def can_use(self, user) -> bool: ...
    def use(self, ctx: UseContext, user) -> bool:
        ctx.log_add(f"{user.get_short_name()} doesn't know how to use {self.name}.")
        return False

@dataclass
class Bandage(Item): # helps with bleed_rate a little
    power: int = 3

    def use(self, ctx: UseContext, user) -> bool:
        if not getattr(user, "alive", True):
            return False

        # Wounded parts that are NOT destroyed
        wounded = [p for p in user.body_parts if p.wounded and p.hp > 0]

        # Prefer unbandaged wounds first
        unbandaged = [p for p in wounded if not p.is_bandaged]
        bandaged = [p for p in wounded if p.is_bandaged]

        if not wounded:
            ctx.log_add(f"{user.get_short_name()} has nothing to bandage.")
            return False

        def severity(p):
            # higher => worse
            if p.hp_max <= 0:
                return 0.0
            return 1.0 - (p.hp / p.hp_max)

        if unbandaged:
            part = max(unbandaged, key=severity)
            part.bandage_ap_left = 100
            part.bandage_bleed_acc = 0
            user.recalc_bleed_rate_from_parts()
            ctx.log_add(f"{user.get_short_name()} applies a bandage to {part.name} (100 AP).")
            return True

        # ---- Fallback: refresh the weakest existing bandage ----
        # (So you can re-wrap / tighten it instead of a frustrating fail.)
        part = min(bandaged, key=lambda p: p.bandage_ap_left)
        part.bandage_ap_left = 100
        part.bandage_bleed_acc = 0
        user.recalc_bleed_rate_from_parts()
        ctx.log_add(f"{user.get_short_name()} re-bandages {part.name} (refresh 100 AP).")
        return True

@dataclass
class IronSupplement(Item): # provides blood regen
    regen: int = 2
    duration: int = 10

    def use(self, ctx: UseContext, user) -> bool:
        user.blood_regen_ticks += self.duration
        user.blood_regen_amount = max(user.blood_regen_amount, self.regen)
        ctx.log_add(f"{user.get_short_name()} takes iron supplements!")
        return True

@dataclass
class Grenade(Item):
    radius: int = 2
    damage: int = 3

    def can_use(self, user) -> bool:
        # TODO: not if arms broken!
        return True

    def use(self, ctx: UseContext, user) -> bool:
        # TODO: 1. bresenham line
        #       2. throw
        #.      3. spawn timer
        #.      4. tick timer
        #.      5. explode
        #.      6. shrapnel
        return True

@dataclass
class Weapon(Item): # equipped into a special 'weapon' slot.
    weapon_data: WeaponData = None
    muzzle_flash: bool = False

    def use(self, ctx: UseContext, user) -> bool:
        # using Weapon means equipping it
        old = user.weapon
        user.weapon = self
        ctx.log_add(f"{user.get_short_name()} equips {self.weapon_data.name}.")
        return False # do not consume


@dataclass
class EquipmentItem(Item):
    slot_str: str = ''
    armor: int = 0

    def use(self, ctx: UseContext, user) -> bool:
        bp = user.get_body_part_from_name(self.slot_str)
        prev = bp.equipment
        bp.equipment = self
        user.inventory.append(prev)

# crate is only openable
@dataclass
class Crate: # TODO: change it to Crate class and add usable Crate
    x: int
    y: int
    kind: CrateKind

    ch: int
    fg: Color
    name: str

    amount: int  # ammo bullets or heal amount

    @staticmethod
    def ammo_crate(x: int, y: int, amount: int = 8) -> "Crate":
        return Crate(x=x, y=y, kind="ammo", ch=ord("A"), fg=(180, 180, 60), name="Ammo Crate", amount=amount)

    @staticmethod
    def med_crate(x: int, y: int, amount: int = 4) -> "Crate":
        return Crate(x=x, y=y, kind="med", ch=ord("+"), fg=(180, 80, 80), name="Medkit", amount=amount)
