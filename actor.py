from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import List, Tuple, Optional
from item import EquipmentItem, Item, WeaponData

Color = Tuple[int, int, int]

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

    equipment: EquipmentItem = None

    bandage_ap_left: int = 0
    bandage_bleed_acc: int = 0

    @property
    def is_bandaged(self) -> bool:
        return self.bandage_ap_left > 0

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

    def equip(self, eq: EquipmentItem):
        self.equipment = eq

@dataclass
class Actor:
    team_id: int  # 0 defenders, 1 attackers
    x: int
    y: int

    ch: int
    fg: Color

    hp: int
    hp_max: int

    weapon: WeaponData # for now weapon data. This is the special weapon slot
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
    occupation: str
    inventory: List[Item]

    alive: bool = True
    blood: int = 100
    blood_max: int = 100
    bleed_rate: int = 0

    # slight bonus to damage. This is the base ability to how easily wounded the soldier can be
    strength: int = 5
    dexterity: int = 5 # affects accuracy and evasion
    constitution: int = 5 # affects hp and survivability

    blood_regen_ticks: int = 0
    blood_regen_amount: int = 0
    bandage_ticks: int = 0 # bandaging means there's 1hp every 20 APs for 100 APs

    body_parts: List[BodyPart] = field(default_factory=lambda: [
        BodyPart("Head", hp=10, hp_max=10, hit_chance_modifier=20, blood_loss_modifier=3.0, healing_time_modifier=0.2, char="O"),
        BodyPart("Neck", hp=20, hp_max=20, hit_chance_modifier=-30, blood_loss_modifier=4.5, healing_time_modifier=0.2, char="|"),
        BodyPart("Torso", hp=20, hp_max=20, hit_chance_modifier=-10, blood_loss_modifier=2.3, healing_time_modifier=1.0, char="X"),
        BodyPart("Left Arm", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=1.5, healing_time_modifier=0.8, char="-"),
        BodyPart("Right Arm", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=1.5, healing_time_modifier=0.8, char="-"),
        BodyPart("Left Hand", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=1, healing_time_modifier=0.5, char="B"),
        BodyPart("Right Hand", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=1, healing_time_modifier=0.8, char="B"),
        BodyPart("Left Leg", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=1, healing_time_modifier=0.8, char="/"),
        BodyPart("Right Leg", hp=10, hp_max=10, hit_chance_modifier=-20, blood_loss_modifier=1, healing_time_modifier=0.8, char="\\"),
        BodyPart("Left Foot", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=1, healing_time_modifier=0.5, char="_"),
        BodyPart("Right Foot", hp=5, hp_max=5, hit_chance_modifier=-40, blood_loss_modifier=1, healing_time_modifier=0.5, char="_")])

    @property
    def defense(self) -> int:
        # for ...
        pass

    def apply_bandage_to_part(self, part_name: str, ap_total: int = 100) -> bool:
        if not self.alive:
            return False

        part = self.get_body_part_from_name(part_name)
        if not part.wounded or part.hp <= 0:
            # either not wounded or destroyed; up to you if bandage should be allowed
            return False

        part.bandage_ap_left = ap_total
        part.bandage_bleed_acc = 0
        return True

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

    def tick_blood_regen(self) -> None:
        self.blood_regen_ticks -= 1
        self.blood = min(self.blood_max, self.blood + self.blood_regen_amount)
        if self.blood_regen_ticks <= 0:
            self.blood_regen_amount = 0
        if self.blood_regen_amount > 0:
            print(f"{self.get_short_name()} regenerates {self.blood_regen_amount} blood!")

    def tick_bandages(self, ap_spent: int) -> int:
        """
        Progress all bandages by ap_spent.
        For each bandaged wound:
        - every 20 AP -> lose 1 blood
        - after 100 AP -> wound is treated (wounded=False), bandage removed
        Returns how much blood was lost due to bandaged wounds this tick.
        """
        if not self.alive or ap_spent <= 0:
            return 0

        blood_loss = 0

        for p in self.body_parts:
            if not p.is_bandaged:
                continue

            p.bandage_ap_left = max(0, p.bandage_ap_left - ap_spent)

            p.bandage_bleed_acc += ap_spent
            while p.bandage_bleed_acc >= 20:
                p.bandage_bleed_acc -= 20
                blood_loss += 1

            if p.bandage_ap_left == 0:
                p.wounded = False
                # broken stays broken

        if blood_loss > 0:
            self.apply_blood_loss(blood_loss)

        return blood_loss

    def recalc_bleed_rate_from_parts(self) -> None:
        rate = 0
        for p in self.body_parts:
            if p.wounded and p.hp > 0 and not p.is_bandaged:
                severity = 1.0 - (p.hp / p.hp_max) #(p.hp / p.hp_max if p.hp_max > 0 else 1.0)
                rate += int(round(p.blood_loss_modifier * (1 + 2 * severity)))

        print(f"Bleeding rate for: {self.get_short_name()}: {rate}")
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

        print(f"Chosen part for {self.get_short_name()}: {part.name}")
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

    def get_body_part_status_and_color(self, name: str) -> Tuple[str, Tuple[int, int, int]]:
        part = next((p for p in self.body_parts if p.name.lower() == name), None)
        if not part:
            return ("Unknown", (120, 120, 120))

        if part.hp_max <= 0:
            return ("Invalid", (120, 120, 120))

        ratio = part.hp / part.hp_max
        ratio = max(0.0, min(1.0, ratio))

        # ---- Status string ----
        if part.hp <= 0:
            status = "Destroyed"
        elif part.broken:
            status = "Broken"
        elif part.wounded:
            status = "Wounded"
        else:
            status = "Healthy"

        if ratio >= 0.5:
            red = int(255 * (1 - ratio) * 2)
            green = 255
        else:
            red = 255
            green = int(255 * ratio * 2)

        blue = 0
        if part.hp <= 0:
            red = 120
            green = 0

        color = (red, green, blue)
        return status, color

    def get_bleeding_status_and_color(self) -> Tuple[str, Tuple[int], Tuple[int]]:
        def is_bandaged(p) -> bool:
            return getattr(p, "bandage_ap_left", 0) > 0

        severity_color_map_fg = {0: (245, 245, 0), 1: (180, 0, 0), 2: (240, 0, 0), 3: (0, 240, 0)}
        severity_color_map_bg_bad = (80,0,0)
        severity_color_map_good = (0,50,0)
        severity_color_map_bg = severity_color_map_good
        status = "No bleeding"
        color_fg = severity_color_map_fg[3]
        if self.bleed_rate > 0:
            if self.bleed_rate >= 5:
                status = f"Severe bleeding! ({self.bleed_rate} HP/tick)"
                color_fg = severity_color_map_fg[1]
                severity_color_map_bg = severity_color_map_bg_bad
            elif self.bleed_rate >= 10:
                status = f"Critical bleeding! ({self.bleed_rate} HP/tick)"
                color_fg = severity_color_map_fg[2]
                severity_color_map_bg = severity_color_map_bg_bad
            else:
                status = f"Bleeding! ({self.bleed_rate} HP/tick)"
                color_fg = severity_color_map_fg[0]
                severity_color_map_bg = severity_color_map_bg_bad
        return (status, color_fg, severity_color_map_bg)


    def get_treatment_status_and_color(self) -> Tuple[str, Tuple[int, int, int], Tuple[int, int, int]]:
        """
        Treatment UI:
        - Untreated wounds (wounded and not bandaged)
        - Bandaged wounds (wounded and bandaged; show remaining AP)
        - Broken parts
        - Iron supplements active (blood regen)
        """

        fg_map = {
            "good": (0, 240, 0),
            "warn": (245, 245, 0),
            "bad":  (240, 0, 0),
            "info": (140, 200, 255),
            "gray": (180, 180, 180),
        }
        bg_bad = (80, 0, 0)
        bg_good = (0, 50, 0)
        bg_info = (0, 30, 60)

        def is_bandaged(p) -> bool:
            return getattr(p, "bandage_ap_left", 0) > 0

        wounded_parts = [p for p in self.body_parts if p.wounded and p.hp > 0]
        broken_parts = [p for p in self.body_parts if p.broken and p.hp > 0]

        untreated = [p for p in wounded_parts if not is_bandaged(p)]
        bandaged = [p for p in wounded_parts if is_bandaged(p)]

        iron_ticks = getattr(self, "blood_regen_ticks", 0)
        iron_amt = getattr(self, "blood_regen_amount", 0)
        iron_active = iron_ticks > 0

        # Base status
        if not wounded_parts and not broken_parts:
            status = "No untreated wounds."
            fg = fg_map["good"]
            bg = bg_good
        else:
            # if anything is untreated, treat as danger/warn
            if broken_parts:
                status = f"Untreated: {len(untreated)} | Bandaged: {len(bandaged)} | Broken: {len(broken_parts)}"
                fg = fg_map["bad"] if len(untreated) > 0 else fg_map["warn"]
                bg = bg_bad
            else:
                status = f"Untreated: {len(untreated)} | Bandaged: {len(bandaged)}"
                fg = fg_map["bad"] if len(untreated) > 0 else (fg_map["warn"] if bandaged else fg_map["good"])
                bg = bg_bad if (len(untreated) > 0) else bg_good

        return (status, fg, bg)

    def get_iron_supplement_status_and_color(self) -> Tuple[Optional[str], Tuple[int, int, int], Tuple[int, int, int]]:
        fg_map = {
            "good": (0, 240, 0),
            "warn": (245, 245, 0),
            "bad":  (240, 0, 0),
            "info": (140, 200, 255),
            "gray": (180, 180, 180),
        }
        bg_info = (0, 30, 60)
        bg = bg_info
        fg = fg_map["good"]
        def is_bandaged(p) -> bool: # wtf is that, just get bandage_ap_left...
            return getattr(p, "bandage_ap_left", 0) > 0

        wounded_parts = [p for p in self.body_parts if p.wounded and p.hp > 0]
        untreated = [p for p in wounded_parts if not is_bandaged(p)]

        iron_ticks = self.blood_regen_ticks
        iron_active = iron_ticks > 0

        status = None
        if untreated and not iron_active:
            status = "No iron supplemented!"
            fg = fg_map['warn']
        elif iron_active:
            status = "Iron supplemented :)"
            fg = fg_map["good"]
        print(iron_active)
        return (status, fg, bg)

    def is_enemy_of(self, other: "Actor") -> bool:
        return self.team_id != other.team_id

    def get_short_name(self) -> str:
        return self.name.split()[0]  # first name only, for compact display on the mapq

    def get_body_part_from_name(self, name: str) -> BodyPart:
        """
        Find a BodyPart by name (case-insensitive) with some friendly alias handling.
        Examples it accepts:
        "Head", "head", " HEAD "
        "Left Arm", "leftarm", "l arm", "l_arm", "left-arm"
        "Right Leg", "rleg", "right_leg"
        "Torso", "body"
        also matches by char if you pass e.g. "O" (Head), "X" (Torso)
        Raises ValueError if not found.
        """
        if not name or not name.strip():
            raise ValueError("get_body_part_from_name: empty name")

        raw = name.strip()

        # Normalize: lower, remove separators
        key = raw.lower().replace("_", " ").replace("-", " ")
        key = " ".join(key.split())  # collapse whitespace

        # Quick match by exact normalized name
        for p in self.body_parts:
            if p.name.lower() == key:
                return p

        # Allow matching by body part char (paperdoll glyph), e.g. "O"
        if len(raw.strip()) == 1:
            c = raw.strip()
            for p in self.body_parts:
                if p.char == c:
                    return p

        # Aliases
        aliases = {
            "body": "torso",
            "chest": "torso",
            "abdomen": "torso",
            "head": "head",
            "neck": "neck",

            "l arm": "left arm",
            "leftarm": "left arm",
            "left arm": "left arm",
            "r arm": "right arm",
            "rightarm": "right arm",
            "right arm": "right arm",

            "l hand": "left hand",
            "lefthand": "left hand",
            "left hand": "left hand",
            "r hand": "right hand",
            "rhand": "right hand",
            "righthand": "right hand",
            "right hand": "right hand",

            "l leg": "left leg",
            "lleg": "left leg",
            "leftleg": "left leg",
            "left leg": "left leg",
            "r leg": "right leg",
            "rleg": "right leg",
            "rightleg": "right leg",
            "right leg": "right leg",

            "l foot": "left foot",
            "lfoot": "left foot",
            "leftfoot": "left foot",
            "left foot": "left foot",
            "r foot": "right foot",
            "rfoot": "right foot",
            "rightfoot": "right foot",
            "right foot": "right foot",
        }

        # Also accept compact forms like "left  arm" already handled by whitespace collapsing
        compact = key.replace(" ", "")
        if compact in aliases:
            key2 = aliases[compact]
        else:
            key2 = aliases.get(key, None)

        if key2 is not None:
            for p in self.body_parts:
                if p.name.lower() == key2:
                    return p

        # As a last resort: substring match (useful for "arm left" typos)
        # Keep it conservative to avoid wrong matches.
        if "arm" in key and "left" in key:
            return next(p for p in self.body_parts if p.name.lower() == "left arm")
        if "arm" in key and "right" in key:
            return next(p for p in self.body_parts if p.name.lower() == "right arm")
        if "leg" in key and "left" in key:
            return next(p for p in self.body_parts if p.name.lower() == "left leg")
        if "leg" in key and "right" in key:
            return next(p for p in self.body_parts if p.name.lower() == "right leg")
        if "hand" in key and "left" in key:
            return next(p for p in self.body_parts if p.name.lower() == "left hand")
        if "hand" in key and "right" in key:
            return next(p for p in self.body_parts if p.name.lower() == "right hand")
        if "foot" in key and "left" in key:
            return next(p for p in self.body_parts if p.name.lower() == "left foot")
        if "foot" in key and "right" in key:
            return next(p for p in self.body_parts if p.name.lower() == "right foot")
        if key in ("torso", "body", "chest"):
            return next(p for p in self.body_parts if p.name.lower() == "torso")

        valid = ", ".join(p.name for p in self.body_parts)
        raise ValueError(f"Unknown body part '{name}'. Valid: {valid}")
