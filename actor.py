from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import List, Tuple, Optional

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
class BodyPart:
    name: str
    hp: int
    hp_max: int
    hit_chance_modifier: float # percent, added to the weapon's base accuracy when targeting this body part
    blood_loss_modifier: float  # how much hp is lost per turn when this body part is wounded. E.g. head wounds cause more bleeding than arm wounds.
    healing_time_modifier: float
    char: str

    wounded: bool = False
    broken: bool = False

    def get_color(self) -> Color:
        # Return a color based on hp percentage. Green when healthy, red when damaged.
        ratio = self.hp / self.hp_max if self.hp_max > 0 else 0
        r = int(255 * (1 - ratio))
        g = int(255 * ratio)
        b = 0
        return (r, g, b)

    def damage(self, amount: int) -> None:
        self.hp = max(0, self.hp - amount)
        if self.hp < self.hp_max:
            self.wounded = True
        if self.hp_max > 0 and (self.hp / self.hp_max) < 0.23:
            self.broken = True

@dataclass
class Actor:
    team_id: int  # 0 defenders, 1 attackers
    x: int
    y: int

    ch: int
    fg: Color

    hp: int
    hp_max: int

    weapon: Weapon
    ammo_in_mag: int
    ammo_reserve: int

    name: str
    rank: str
    nationality: str
    political_views: str
    title: str
    university: str
    worldview: str
    favorite_sentence: str
    favorite_dish: str

    alive: bool = True
    blood: int = 100
    blood_max: int = 100
    bleed_rate: int = 0

    # slight bonus to damage. This is the base ability to how easily wounded the soldier can be
    strength: int = 5
    dexterity: int = 5 # affects accuracy and evasion
    constitution: int = 5 # affects hp and survivability

    body_parts: List[BodyPart] = field(default_factory=lambda: [
        BodyPart("Head", hp=10, hp_max=10, hit_chance_modifier=20, blood_loss_modifier=0.5, healing_time_modifier=2.0, char="O"),
        BodyPart("Neck", hp=5, hp_max=20, hit_chance_modifier=-30, blood_loss_modifier=2, healing_time_modifier=0.2, char="|"),
        BodyPart("Torso", hp=20, hp_max=20, hit_chance_modifier=-10, blood_loss_modifier=1.0, healing_time_modifier=1.0, char="X"),
        BodyPart("Left Arm", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=0.8, healing_time_modifier=0.8, char="-"),
        BodyPart("Right Arm", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=0.8, healing_time_modifier=0.8, char="-"),
        BodyPart("Left Hand", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=0.3, healing_time_modifier=0.5, char="B"),
        BodyPart("Right Hand", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=0.8, healing_time_modifier=0.8, char="B"),
        BodyPart("Left Leg", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=0.8, healing_time_modifier=0.8, char="/"),
        BodyPart("Right Leg", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=0.8, healing_time_modifier=0.8, char="\\"),
        BodyPart("Left Foot", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=0.3, healing_time_modifier=0.5, char="_"),
        BodyPart("Right Foot", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=0.3, healing_time_modifier=0.5, char="_")])

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

    def choose_hit_part(self, acc: int) -> BodyPart:
        # weights based on hit chance modifier; higher modifier => more likely to be hit
        # We'll convert modifiers into positive weights.
        parts = self.body_parts
        weights = []
        for p in parts:
            # Base weight 10 plus (modifier+acc%2)/2, clamped
            w = 10 + int(p.hit_chance_modifier + acc % 10 / 2)
            w = max(1, min(30, w))
            weights.append(w)
        return random.choices(parts, weights=weights, k=1)[0]

    def apply_blood_loss(self, amount: int) -> None:
        if not self.alive:
            return
        self.blood = max(0, self.blood - max(0, amount))
        if self.blood <= 0:
            self.alive = False

    def tick_bleeding(self) -> int:
        if not self.alive:
            return 0
        # TODO: Apply constitution. If mitigated, log that is was mitigated by being tough or something.
        loss = max(0, self.bleed_rate) #- self.constitution//2) # constitution helps mitigate blood loss
        if loss > 0:
            print(f"{self.get_short_name()} bleeds for {loss} blood.")
            self.apply_blood_loss(loss)
        return loss

    def recalc_bleed_rate_from_parts(self) -> None:
        rate = 0
        for p in self.body_parts:
            if p.wounded and p.hp > 0:
                severity = 1.0 - (p.hp / p.hp_max if p.hp_max > 0 else 1.0)
                rate += int(round(p.blood_loss_modifier * (1 + 2 * severity)))
        self.bleed_rate = max(0, rate)

    def take_hit(self, damage: int, acc: int) -> BodyPart:
        if not self.alive:
            return self.body_parts[2]

        part = self.choose_hit_part(acc)
        part.damage(damage) # strength adds a flat bonus to damage
        self.apply_blood_loss(damage)
        self.recalc_bleed_rate_from_parts()

        if part.name in ("Head", "Neck", "Torso") and part.hp == 0:
            self.alive = False
            self.blood = 0

        return part

    def get_status_strings(self) -> List[str]:
        s = []
        if self.bleed_rate > 0:
            s.append(f"Bleeding ({self.bleed_rate}/turn)")
        if any(p.wounded for p in self.body_parts):
            s.append("Wounded")
        if any(p.broken and "Arm" in p.name for p in self.body_parts):
            s.append("Arm broken")
        if any(p.broken and "Leg" in p.name for p in self.body_parts):
            s.append("Leg broken")
        head = next(p for p in self.body_parts if p.name == "Head")
        neck = next(p for p in self.body_parts if p.name == "Neck")
        if head.wounded or neck.wounded:
            s.append("Concussed")
        return s

    def is_enemy_of(self, other: "Actor") -> bool:
        return self.team_id != other.team_id

    def get_short_name(self) -> str:
        return self.name.split()[0]  # first name only, for compact display on the map
