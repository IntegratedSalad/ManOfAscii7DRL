from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple
import random
import math

import tcod
import tcod.event

from actor import Actor, RIFLE, SMG, SNIPER
from item import Item
from map import SAND, GameMap, ROCK, DOOR
from screen import ScreenLayout
import textwrap

ImpactType = Literal["actor", "tile", "none"]

@dataclass
class PendingImpact:
    impact_type: ImpactType
    actor: Optional[Actor]
    tile_xy: Optional[Tuple[int, int]]
    shooter_name: str
    damage: int
    acc: int
    roll: int
    is_hit_roll: bool

@dataclass
class MessageLog:
    lines: List[str]
    layout: ScreenLayout

    def add(self, msg: str) -> None:
        self.lines.append(msg)
        if len(self.lines) > 200:
            self.lines = self.lines[-200:]

        # wrap messages
        wrapped = []
        for line in self.lines:
            wrapped.extend(textwrap.wrap(line, self.layout.log_rect.w - 2))
        self.lines = wrapped

    # add support for colors e.g. by storing List[Tuple[str, Color]] and adjusting rendering

class Engine:
    def __init__(self, game_map: GameMap, layout: ScreenLayout) -> None:
        self.game_map = game_map
        self.layout = layout

        self.actors: List[Actor] = []
        self.items: List[Item] = []

        # bullet animation state: path and current index
        self.bullet_path: List[Tuple[int,int]] = []
        self.bullet_index: int = 0  # which step is currently visible
        self.bullet_timer = 0.0  # time accumulator for advancing bullet animation
        self.bullet_step_time = 0.03  # time per step in seconds

        self.log = MessageLog(lines=[], layout=self.layout)
        self.running = True

        self.current_team: int = 1  # 1 attackers start, 0 defenders
        self.team_ap = {0: 10, 1: 10}
        self.team_ap_max = 10

        self.selected_index: int = 0  # index within filtered list of current team alive actors

        # Aiming mode
        self.aiming: bool = False
        self.aim_x: int = 0
        self.aim_y: int = 0

        self.turn_count: int = 1
        self.crate_every_n_turns: int = 4

        self.pending_impact: Optional[PendingImpact] = None

    def setup_demo_match(self) -> None:
        w, h = self.game_map.w, self.game_map.h

        self.actors.append(Actor(0, w // 2 - 3, 3, "Def-1", ord("D"), (120, 180, 255), 10, 10, RIFLE, 6, 12))
        self.actors.append(Actor(0, w // 2, 2, "Def-2", ord("D"), (120, 180, 255), 10, 10, SMG, 10, 10))
        self.actors.append(Actor(0, w // 2 + 3, 4, "Def-3", ord("D"), (120, 180, 255), 10, 10, SNIPER, 4, 8))

        y0 = h - 10
        self.actors.append(Actor(1, w // 2 - 3, y0, "Atk-1", ord("A"), (255, 180, 120), 10, 10, RIFLE, 6, 12))
        self.actors.append(Actor(1, w // 2, y0 + 1, "Atk-2", ord("A"), (255, 180, 120), 10, 10, SMG, 10, 10))
        self.actors.append(Actor(1, w // 2 + 3, y0, "Atk-3", ord("A"), (255, 180, 120), 10, 10, SNIPER, 4, 8))

        self.team_ap[0] = self.team_ap_max
        self.team_ap[1] = self.team_ap_max

        self._clamp_selection()
        sel = self.get_selected_actor()
        if sel:
            self.aim_x, self.aim_y = sel.x, sel.y

        self.log.add("Controls: Arrows move | Tab cycle | F aim/fire | R reload | G pickup | Space end turn | Esc quit")

    def alive_actors(self) -> List[Actor]:
        return [a for a in self.actors if a.alive]

    def team_actors(self, team_id: int) -> List[Actor]:
        return [a for a in self.actors if a.alive and a.team_id == team_id]

    def enemy_actors(self, team_id: int) -> List[Actor]:
        return [a for a in self.actors if a.alive and a.team_id != team_id]

    def actor_at(self, x: int, y: int) -> Optional[Actor]:
        for a in self.alive_actors():
            if a.x == x and a.y == y:
                return a
        return None

    def item_at(self, x: int, y: int) -> Optional[Item]:
        for it in self.items:
            if it.x == x and it.y == y:
                return it
        return None

    def get_selected_actor(self) -> Optional[Actor]:
        team_list = self.team_actors(self.current_team)
        if not team_list:
            return None
        self.selected_index = max(0, min(self.selected_index, len(team_list) - 1))
        return team_list[self.selected_index]

    def _clamp_selection(self) -> None:
        team_list = self.team_actors(self.current_team)
        if not team_list:
            self.selected_index = 0
        else:
            self.selected_index = max(0, min(self.selected_index, len(team_list) - 1))

    def _check_victory(self) -> None:
        if not self.team_actors(0):
            self.log.add("Attackers win! (All defenders down)")
            self.running = False
        elif not self.team_actors(1):
            self.log.add("Defenders win! (All attackers down)")
            self.running = False

    MOVE_COST = 0
    SHOOT_COST = 3
    RELOAD_COST = 2
    PICKUP_COST = 2

    def update(self, dt: float) -> None:
        if not self.bullet_path:
            return

        dt = min(dt, 0.05)

        self.bullet_timer += dt
        if self.bullet_timer >= self.bullet_step_time:
            self.bullet_timer = 0.0
            self.bullet_index += 1 # here advance the bullet "animation" after timer exceeds step time

            if self.bullet_index >= len(self.bullet_path):
                self.bullet_path = []
                self.bullet_index = 0
                self._resolve_pending_impact()

    def _resolve_pending_impact(self) -> None:
        if not self.pending_impact:
            return

        imp = self.pending_impact
        self.pending_impact = None

        if imp.impact_type == "actor" and imp.actor and imp.actor.alive:
            imp.actor.take_damage(imp.damage)
            self.log.add(f"{imp.shooter_name} shoots and hits {imp.actor.name} for {imp.damage} damage! (Acc: {imp.acc}%, Roll: {imp.roll})")

            friendly_fire = imp.actor.team_id == imp.actor.team_id
            if friendly_fire:
                self.log.add(f"Friendly fire from {imp.actor.name}! Idiot!")

            if not imp.actor.alive:
                self.log.add(f"{imp.actor.name} is down!")
                if not friendly_fire:
                    self._check_victory()
                else:
                    insults = ["Fucking cretin!", "Bro wtf", "Open your fucking eyes maybe??", "What the fuck, it was his birthday!"]
                    self.log.add(f"{random.choice(insults)}")
            return

        if imp.impact_type == "tile" and imp.tile_xy:
            x, y = imp.tile_xy
            if self.game_map.tile_at(x, y) == DOOR:
                self.game_map.set_tile(x, y, SAND)
                self.log.add(f"{imp.shooter_name} blows open the door!")
            else:
                self.log.add(f"{imp.shooter_name} hits {self.game_map.tile_at(x,y).name}.")
            return

        self.log.add(f"{imp.shooter_name} fires.")


    def is_bullet_animation_active(self) -> bool:
        return len(self.bullet_path) > 0

    def handle_event(self, event: tcod.event.Event) -> None:
        if isinstance(event, tcod.event.Quit):
            self.running = False
            return

        if isinstance(event, tcod.event.KeyDown):
            self._handle_keydown(event)

        if isinstance(event, tcod.event.MouseMotion):
            # optional: could set aim cursor from mouse if you want later
            pass

    def _handle_keydown(self, ev: tcod.event.KeyDown) -> None:

        if self.is_bullet_animation_active():
            return

        if ev.sym == tcod.event.KeySym.ESCAPE:
            if self.aiming:
                self.aiming = False
                self.log.add("Aiming cancelled.")
            else:
                self.running = False
            return

        if ev.sym == tcod.event.KeySym.TAB:
            self._cycle_selected(+1)
            return

        if ev.sym == tcod.event.KeySym.SPACE:
            self.end_turn()
            return

        if ev.sym == tcod.event.KeySym.O:
            self.try_open_door()
            return

        dx, dy = 0, 0
        if ev.sym == tcod.event.KeySym.UP:
            dy = -1
        elif ev.sym == tcod.event.KeySym.DOWN:
            dy = 1
        elif ev.sym == tcod.event.KeySym.LEFT:
            dx = -1
        elif ev.sym == tcod.event.KeySym.RIGHT:
            dx = 1

        if dx != 0 or dy != 0:
            if self.aiming:
                self._move_aim(dx, dy)
            else:
                self.try_move_selected(dx, dy)
            return

        # Actions
        if ev.sym == tcod.event.KeySym.f:
            if not self.aiming:
                sel = self.get_selected_actor()
                if not sel:
                    return
                self.aiming = True
                self.aim_x, self.aim_y = sel.x, sel.y
                self.log.add("Aiming: move cursor with arrows, Enter to shoot, Esc to cancel.")
            return

        if ev.sym == tcod.event.KeySym.RETURN:
            if self.aiming:
                self.try_shoot_at_cursor()
            return

        if ev.sym == tcod.event.KeySym.r:
            self.try_reload_selected()
            return

        if ev.sym == tcod.event.KeySym.g:
            self.try_pickup()
            return

    # ----------------- Turn / Actions -----------------
    def _cycle_selected(self, delta: int) -> None:
        team_list = self.team_actors(self.current_team)
        if not team_list:
            return
        self.selected_index = (self.selected_index + delta) % len(team_list)
        sel = self.get_selected_actor()
        if sel:
            self.aim_x, self.aim_y = sel.x, sel.y

    def end_turn(self) -> None:

        self.aiming = False
        self.current_team = 1 - self.current_team
        self.team_ap[self.current_team] = self.team_ap_max
        self._clamp_selection()

        self.turn_count += 1
        self.log.add(f"--- Turn {self.turn_count}: {'Attackers' if self.current_team==1 else 'Defenders'} ---")

        # TODO: Add summary of damage of the last turn, e.g. "Def-2 took 3 damage, Atk-1 took 4 damage"

        # Spawn crates at end of a full round (both teams took turns) -> approximate by every N turns
        if self.turn_count % self.crate_every_n_turns == 0:
            self.spawn_random_crate()

        self._check_victory()

    def _spend_ap(self, cost: int) -> bool:
        if self.team_ap[self.current_team] < cost:
            self.log.add("Not enough AP.")
            return False
        self.team_ap[self.current_team] -= cost
        return True

    def try_move_selected(self, dx: int, dy: int) -> None:
        sel = self.get_selected_actor()
        nx, ny = sel.x + dx, sel.y + dy
        tile_cost = self.game_map.return_movement_cost(nx, ny)
        if not sel or not sel.alive:
            return
        if not self._spend_ap(self.MOVE_COST + tile_cost):
            return

        if self.game_map.tile_at(nx, ny) == DOOR:
            self.log.add("The door is closed.")
            self.team_ap[self.current_team] += self.MOVE_COST + tile_cost
            return

        if not self.game_map.is_walkable(nx, ny):
            self.log.add("Blocked terrain.")
            self.team_ap[self.current_team] += self.MOVE_COST + tile_cost
            return
        if self.actor_at(nx, ny) is not None:
            self.log.add("Tile occupied.")
            self.team_ap[self.current_team] += self.MOVE_COST + tile_cost
            return

        sel.x, sel.y = nx, ny
        self.aim_x, self.aim_y = sel.x, sel.y

    def try_open_door(self) -> None:
        sel = self.get_selected_actor()
        if not sel or not sel.alive:
            return
        if not self._spend_ap(self.MOVE_COST):
            return

        # Check adjacent tiles for a door
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = sel.x + dx, sel.y + dy
            if self.game_map.tile_at(nx, ny) == DOOR:
                self.game_map.set_tile(nx, ny, SAND)
                self.log.add(f"{sel.name} opens the door.")
                return

        self.log.add("No door adjacent to open.")
        self.team_ap[self.current_team] += self.MOVE_COST  # refund for QoL

    def _move_aim(self, dx: int, dy: int) -> None:
        self.aim_x = max(0, min(self.game_map.w - 1, self.aim_x + dx))
        self.aim_y = max(0, min(self.game_map.h - 1, self.aim_y + dy))

    def try_reload_selected(self) -> None:
        sel = self.get_selected_actor()
        if not sel or not sel.alive:
            return
        if not sel.can_reload():
            self.log.add("Cannot reload.")
            return
        if not self._spend_ap(self.RELOAD_COST):
            return

        loaded = sel.reload()
        self.log.add(f"{sel.name} reloads (+{loaded}).")

    def try_pickup(self) -> None:
        sel = self.get_selected_actor()
        if not sel or not sel.alive:
            return
        it = self.item_at(sel.x, sel.y)
        if not it:
            self.log.add("Nothing to pick up.")
            return
        if not self._spend_ap(self.PICKUP_COST):
            return

        if it.kind == "ammo":
            sel.ammo_reserve += it.amount
            self.log.add(f"{sel.name} picks up ammo (+{it.amount}).")
        elif it.kind == "med":
            before = sel.hp
            sel.hp = min(sel.hp_max, sel.hp + it.amount)
            self.log.add(f"{sel.name} uses medkit (+{sel.hp - before} HP).")

        self.items.remove(it)

    def miss_offset_by_acc_(self, acc: int) -> int:
        # If roll >= acc, so offset decreases with accuracy increase
        if acc >= 95: return 1
        if acc >= 90: return 4
        if acc >= 80: return 5
        if acc >= 70: return 10
        if acc >= 60: return 10
        if acc >= 50: return 25
        if acc >= 40: return 30
        if acc >= 30: return 30
        if acc >= 20: return 40
        if acc >= 10: return 45
        return 50

    def pick_miss_endpoint(
            self,
            sx: int,
            sy: int,
            tx: int,
            ty: int,
            acc: int,
            map_w: int,
            map_h: int
        ) -> Tuple[int, int]:
        k = self.miss_offset_by_acc_(acc)
        if k <= 0:
            return tx, ty

        dx = tx - sx
        dy = ty - sy
        length = max(1, abs(dx) + abs(dy))

        pdx, pdy = -dy, dx
        m = max(1, abs(pdx) + abs(pdy))
        pdx /= m
        pdy /= m

        lateral = random.randint(-k, k)
        forward = random.randint(-max(1, k // 4), max(1, k // 4))

        mx = int(round(tx + pdx * lateral + (dx / length) * forward))
        my = int(round(ty + pdy * lateral + (dy / length) * forward))

        mx = max(0, min(map_w - 1, mx))
        my = max(0, min(map_h - 1, my))
        return mx, my

    def try_shoot_at_cursor(self) -> None:
        shooter = self.get_selected_actor()
        if not shooter or not shooter.alive:
            return
        if not self._spend_ap(self.SHOOT_COST):
            return

        if shooter.ammo_in_mag <= 0:
            self.log.add("Click! No ammo in mag.")
            self.team_ap[self.current_team] += self.SHOOT_COST
            return

        tx, ty = self.aim_x, self.aim_y
        if tx == shooter.x and ty == shooter.y:
            self.team_ap[self.current_team] += self.SHOOT_COST
            return

        target = self.actor_at(tx, ty)

        shooter.ammo_in_mag -= 1

        # Range + LOS check
        dist = abs(tx - shooter.x) + abs(ty - shooter.y)
        # if dist > shooter.weapon.range:
        #     self.log.add("Out of range.")
        #     return
        if not self.game_map.los(shooter.x, shooter.y, tx, ty):
            self.log.add("No line of sight.")
            return

        # Accuracy calc
        acc = shooter.weapon.base_accuracy
        # Distance penalty after 5 tiles TODO: calculate the penalty based on the weapon range
        if dist > 5:
            acc -= 2 * (dist - 5)

        if target:
            acc -= self.game_map.cover_bonus_at(target.x, target.y)

        to_hit_roll = random.randint(1, 100)
        acc = max(5, min(95, acc))
        is_hit = to_hit_roll <= acc

        bx, by = tx, ty
        if not is_hit:
            # offset the bullet path (tx,ty) taking accuracy into account when the roll <= acc
            bx, by = self.pick_miss_endpoint(shooter.x, shooter.y, tx, ty, acc, self.game_map.w, self.game_map.h)
            self.log.add(f"{shooter.name}'s hand shakes!")

        line = tcod.los.bresenham((shooter.x, shooter.y), (bx, by)).tolist()
        path: List[Tuple[int, int]] = []

        impact_actor: Optional[Actor] = None
        impact_tile: Optional[Tuple[int, int]] = None

        for x, y in line[1:]:
            x, y = int(x), int(y)
            path.append((x, y))

            a = self.actor_at(x, y)
            if a and a.alive:
                impact_actor = a
                break

            if self.game_map.blocks_los(x, y):
                impact_tile = (x, y)
                break

        self.bullet_path = path
        self.bullet_index = 0
        self.bullet_timer = 0.0

        if impact_actor is not None:
            self.pending_impact = PendingImpact(
                impact_type="actor",
                actor=impact_actor,
                tile_xy=None,
                shooter_name=shooter.name,
                damage=shooter.weapon.damage,
                acc=acc,
                roll=to_hit_roll,
                is_hit_roll=is_hit
            )
        elif impact_tile is not None:
            self.pending_impact = PendingImpact(
                impact_type="tile",
                actor=None,
                tile_xy=impact_tile,
                shooter_name=shooter.name,
                damage=0,
                acc=acc,
                roll=to_hit_roll,
                is_hit_roll=is_hit
            )
        else:
            self.pending_impact = PendingImpact(
                impact_type="none",
                actor=None,
                tile_xy=None,
                shooter_name=shooter.name,
                damage=0,
                acc=acc,
                roll=to_hit_roll,
                is_hit_roll=is_hit
            )

        # Allow blowing up doors
        # if not target: #or target.team_id == shooter.team_id:
        #     if self.game_map.tile_at(tx, ty) == DOOR:
        #         self.game_map.set_tile(tx, ty, SAND)
        #         self.log.add(f"{shooter.name} shoots and blows open the door!")
        #     else:
        #         self.log.add(f"{shooter.name} fires.")
        # else:
        #     friendly_fire = target.team_id == shooter.team_id
        #     if friendly_fire:
        #         self.log.add(f"Friendly fire from {shooter.name}! Idiot!")

        #     if to_hit_roll <= acc:
        #         target.take_damage(shooter.weapon.damage)
        #         self.log.add(f"{shooter.name} hits {target.name} ({shooter.weapon.damage} dmg) [{to_hit_roll} <= {acc}]")
        #         if not target.alive:
        #             self.log.add(f"{target.name} is DOWN!")
        #             if not friendly_fire:
        #                 self._check_victory()
        #             else:
        #                 # choose random insult for friendly fire
        #                 insults = ["Fucking cretin!", "Bro wtf", "Open your fucking eyes maybe??", "What the fuck, it was his birthday!"]
        #                 self.log.add(f"{random.choice(insults)}")
        #     else:
        #         self.log.add(f"{shooter.name} misses {target.name} [{to_hit_roll} > {acc}]")
        #         if friendly_fire:
        #             self.log.add(f"{target.name}: Bro you nearly fucking shot me")

    # ----------------- Crates -----------------
    def spawn_random_crate(self) -> None:
        # Spawn somewhere walkable and empty, preferably mid-map
        attempts = 200
        for _ in range(attempts):
            x = random.randint(0, self.game_map.w - 1)
            y = random.randint(self.game_map.h // 4, (self.game_map.h * 3) // 4)
            if not self.game_map.is_walkable(x, y):
                continue
            if self.actor_at(x, y) is not None:
                continue
            if self.item_at(x, y) is not None:
                continue

            if random.random() < 0.5:
                it = Item.ammo_crate(x, y, amount=random.choice([6, 8, 10]))
            else:
                it = Item.med_crate(x, y, amount=random.choice([3, 4, 5]))
            self.items.append(it)
            self.log.add(f"A crate drops at ({x},{y})!")
            return

    def render(self, con: tcod.Console) -> None:
        self._render_map(con)
        self._render_soldiers_panel(con)
        self._render_equip_panel(con)
        self._render_log_panel(con)

    def _render_map(self, con: tcod.Console) -> None:
        r = self.layout.map_rect

        # draw tiles
        for y in range(self.game_map.h):
            for x in range(self.game_map.w):
                t = self.game_map.tile_at(x, y)
                con.print(x=r.x + x, y=r.y + y, string=chr(t.ch), fg=t.fg, bg=t.bg)

        for it in self.items:
            con.print(r.x + it.x, r.y + it.y, chr(it.ch), fg=it.fg)

        for a in self.alive_actors():
            con.print(r.x + a.x, r.y + a.y, chr(a.ch), fg=a.fg)

        sel = self.get_selected_actor()
        if sel:
            con.print(r.x + sel.x, r.y + sel.y, "X", fg=(255, 255, 255))

        if self.aiming and sel:
            con.print(r.x + self.aim_x, r.y + self.aim_y, "+", fg=(255, 255, 255))
            # draw thin line (dots) for feedback
            for x, y in tcod.los.bresenham((sel.x, sel.y), (self.aim_x, self.aim_y)).tolist():
                if (x, y) == (sel.x, sel.y) or (x, y) == (self.aim_x, self.aim_y):
                    continue
                con.print(r.x + x, r.y + y, "·", fg=(140, 140, 140))

            # Show hit chance if aiming at enemy
            target = self.actor_at(self.aim_x, self.aim_y)
            if target and target.team_id != sel.team_id:
                dist = abs(self.aim_x - sel.x) + abs(self.aim_y - sel.y)
                cover = self.game_map.cover_bonus_at(target.x, target.y)
                acc = sel.weapon.base_accuracy
                if dist > 5:
                    acc -= 2 * (dist - 5)
                acc -= cover
                acc = max(5, min(95, acc))
                con.print(r.x + 1, r.y + 1, f"Hit% {acc}  (cover {cover})", fg=(220, 220, 220))

        if self.bullet_path:
            bx, by = self.bullet_path[self.bullet_index]
            con.print(r.x + bx, r.y + by, "*", fg=(255, 220, 100))

        con.print(r.x + 1, r.y + 0, f"Team: {'ATK' if self.current_team==1 else 'DEF'}  AP: {self.team_ap[self.current_team]}/{self.team_ap_max}", fg=(220, 220, 220))

    def _panel_frame(self, con: tcod.Console, x: int, y: int, w: int, h: int, title: str) -> None:
        con.draw_frame(x, y, w, h, title=title, clear=False, fg=(160, 160, 160))

    def _render_soldiers_panel(self, con: tcod.Console) -> None:
        r = self.layout.soldiers_rect
        self._panel_frame(con, r.x, r.y, r.w, r.h, "Soldiers")

        y = r.y + 1
        sel = self.get_selected_actor()

        def draw_team(team_id: int, label: str) -> None:
            nonlocal y
            header_fg = (255, 200, 140) if team_id == 1 else (140, 200, 255)
            turn_marker = " <" if team_id == self.current_team else ""
            con.print(r.x + 1, y, f"{label}{turn_marker}", fg=header_fg)
            y += 1

            team_list = [a for a in self.actors if a.alive and a.team_id == team_id]
            if not team_list:
                con.print(r.x + 2, y, "(none)", fg=(120, 120, 120))
                y += 1
                return

            for idx, a in enumerate(team_list):
                is_selected = (sel is a)
                fg = (255, 255, 255) if is_selected else (200, 200, 200)
                con.print(
                    r.x + 2,
                    y,
                    f"{a.name:6} HP {a.hp:2}/{a.hp_max:2}  {a.ammo_in_mag:2}/{a.weapon.mag_size:2}+{a.ammo_reserve:2}",
                    fg=fg,
                )
                y += 1

        draw_team(1, "ATK")
        y += 1
        draw_team(0, "DEF")

    def _render_equip_panel(self, con: tcod.Console) -> None:
        r = self.layout.equip_rect
        self._panel_frame(con, r.x, r.y, r.w, r.h, "Selected")

        sel = self.get_selected_actor()
        if not sel:
            con.print(r.x + 1, r.y + 2, "No selection", fg=(120, 120, 120))
            return

        con.print(r.x + 1, r.y + 2, f"{sel.name} ({'ATK' if sel.team_id==1 else 'DEF'})", fg=(255, 255, 255))
        con.print(r.x + 1, r.y + 3, f"Pos: ({sel.x},{sel.y})", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 4, f"Weapon: {sel.weapon.name}", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 5, f"Range {sel.weapon.range}  Acc {sel.weapon.base_accuracy}%", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 6, f"Dmg {sel.weapon.damage}  Ammo {sel.ammo_in_mag}/{sel.weapon.mag_size} +{sel.ammo_reserve}", fg=(200, 200, 200))

        it = self.item_at(sel.x, sel.y)
        if it:
            con.print(r.x + 1, r.y + 8, f"On tile: {it.name} (G)", fg=(220, 220, 180))

    def _render_log_panel(self, con: tcod.Console) -> None:
        r = self.layout.log_rect
        self._panel_frame(con, r.x, r.y, r.w, r.h, "Messages")

        # Show last lines
        max_lines = r.h - 2
        lines = self.log.lines[-max_lines:]
        y = r.y + 1
        for line in lines:
            con.print(r.x + 1, y, line[: r.w - 2], fg=(200, 200, 200))
            y += 1
