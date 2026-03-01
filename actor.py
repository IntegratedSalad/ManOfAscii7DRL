from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional

Color = Tuple[int, int, int]


@dataclass
class Weapon: # move it to the item.py, as weapons will drop upon death, and can be picked up by other actors.
    name: str
    range: int
    base_accuracy: int  # percent
    damage: int
    mag_size: int


RIFLE = Weapon("Rifle", range=12, base_accuracy=70, damage=3, mag_size=6)
SMG = Weapon("SMG", range=8, base_accuracy=65, damage=2, mag_size=10)
SNIPER = Weapon("Sniper", range=16, base_accuracy=80, damage=4, mag_size=4)


@dataclass
class Actor:
    team_id: int  # 0 defenders, 1 attackers
    x: int
    y: int
    name: str

    ch: int
    fg: Color

    hp: int
    hp_max: int

    weapon: Weapon
    ammo_in_mag: int
    ammo_reserve: int

    alive: bool = True

    def can_reload(self) -> bool:
        return self.alive and self.ammo_in_mag < self.weapon.mag_size and self.ammo_reserve > 0

    def reload(self) -> int:
        """Returns number of bullets loaded."""
        if not self.can_reload():
            return 0
        need = self.weapon.mag_size - self.ammo_in_mag
        loaded = min(need, self.ammo_reserve)
        self.ammo_in_mag += loaded
        self.ammo_reserve -= loaded
        return loaded

    def take_damage(self, dmg: int) -> None:
        if not self.alive:
            return
        self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def is_enemy_of(self, other: "Actor") -> bool:
        return self.team_id != other.team_id
