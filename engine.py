from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple
import random
import math
import tcod
import tcod.event

from actor import Actor
from item import Crate, SMG, RIFLE, SNIPER
from map import SAND, TREE, GameMap, ROCK, DOOR
from screen import ScreenLayout
import textwrap
from utils import *
from enum import Enum, auto
from name_generation import *
from item import Bandage, IronSupplement

class UIState(Enum):
    PLAY = auto()
    CHAR_SHEET = auto()
    INVENTORY = auto()

class SheetTab(Enum):
    OVERVIEW = auto()
    INVENTORY = auto()
    WOUNDS = auto()
    BIO = auto()

ImpactType = Literal["actor", "tile", "none"]

@dataclass
class PendingImpact:
    impact_type: ImpactType
    actor: Optional[Actor]
    tile_xy: Optional[Tuple[int, int]]
    shooter_obj: Actor
    damage: int
    acc: int
    roll: int
    is_hit_roll: bool

@dataclass
class ColorStr:
    text: str
    colorfg: Tuple[int, int, int]
    colorbg: Tuple[int, int, int]
    blink: bool = False

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
    def __init__(
        self,
        maps_grid: List[List[GameMap]],
        crates_grid: List[List[List[Crate]]],
        layout: ScreenLayout,
        start_gx: int = 1,
        start_gy: int = 2,
    ) -> None:
        self.layout = layout

        # --- world grid ---
        self.maps_grid = maps_grid
        self.crates_grid = crates_grid
        self.grid_h = len(maps_grid)
        self.grid_w = len(maps_grid[0]) if self.grid_h > 0 else 0

        self.gx = max(0, min(self.grid_w - 1, start_gx))
        self.gy = max(0, min(self.grid_h - 1, start_gy))

        self.game_map: GameMap = self.maps_grid[self.gy][self.gx]
        self.spawned_enemy_cells: set[tuple[int, int]] = set()

        # --- UI ---
        self.ui_mode = UIState.PLAY
        self.sheet_tab = SheetTab.OVERVIEW
        self.sheet_scroll = 0

        # --- entities ---
        self.actors: List[Actor] = []
        self.crates: List[Crate] = []
        self._load_current_cell_crates()

        # --- bullet animation ---
        self.bullet_path: List[Tuple[int, int]] = []
        self.bullet_index: int = 0
        self.bullet_timer = 0.0
        self.bullet_step_time = 0.03

        self.log = MessageLog(lines=[], layout=self.layout)
        self.running = True

        self.current_team: int = 1
        self.team_ap = {0: 20, 1: 20}
        self.team_ap_max = 20

        self.selected_index: int = 0
        self.inv_index = 0

        self.aiming: bool = False
        self.aim_x: int = 0
        self.aim_y: int = 0

        self.turn_count: int = 1
        self.crate_every_n_turns: int = 4

        self.pending_impact: Optional[PendingImpact] = None

    def _load_current_cell_crates(self) -> None:
        """Load crates for current grid cell into self.crates."""
        self.crates = list(self.crates_grid[self.gy][self.gx])

    def _save_current_cell_crates(self) -> None:
        """Persist current self.crates back into the grid cell (so pickups remain gone)."""
        self.crates_grid[self.gy][self.gx] = list(self.crates)

    def try_change_map(self, dx: int, dy: int) -> bool:
        """Switch to neighboring map cell. Returns True on success."""
        nx = self.gx + dx
        ny = self.gy + dy
        if nx < 0 or nx >= self.grid_w or ny < 0 or ny >= self.grid_h:
            return False

        # save current cell state
        self._save_current_cell_crates()

        # switch
        self.gx, self.gy = nx, ny
        self.game_map = self.maps_grid[self.gy][self.gx]
        self._load_current_cell_crates()
        if not getattr(self.game_map, "blood", None):
            self.game_map.set_blood()

        self._spawn_enemies_for_current_cell()
        self.log.add(f"Entered area ({self.gx},{self.gy}).")
        self._clamp_selection()
        sel = self.get_selected_actor()
        if sel:
            self.aim_x, self.aim_y = sel.x, sel.y
        return True

    def setup_demo_match(self) -> None:
        w, h = self.game_map.w, self.game_map.h

        def make_starting_inventory():
            # fresh instances each time (no shared item objects across soldiers)
            return [
                Bandage(
                    name="Bandage",
                    ch=ord("#"),
                    fg=(245, 245, 221),
                    stackable=True,
                    qty=2,
                    power=3,
                ),
                IronSupplement(
                    name="Iron Supplement",
                    ch=ord("!"),
                    fg=(255, 255, 255),
                    stackable=True,
                    qty=10,
                    regen=2,
                    duration=12,
                ),
            ]

        def spawn_soldier(
            team_id: int,
            x: int,
            y: int,
            weapon,
            ammo_in_mag: int,
            ammo_reserve: int,
            fg,
        ) -> None:
            rand_data = generate_random_soldier_info()
            inv = make_starting_inventory()

            a = Actor(
                team_id,
                x,
                y,
                ord("☻"),
                fg,
                10,
                10,
                weapon,
                ammo_in_mag,
                ammo_reserve,
                inventory=inv,
                **rand_data,
            )
            # IMPORTANT: put the actor into the *current* map cell
            a.gx, a.gy = self.gx, self.gy
            self.actors.append(a)

        # --- spawn player team in current cell ---
        # Decide who the "player team" is; your code uses current_team=1 initially.
        # If you want player to control team 1 (ATK), spawn team 1 here.
        player_team = 1
        player_fg = (255, 180, 120) if player_team == 1 else (120, 180, 255)

        y0 = h - 10  # bottom-ish
        spawn_soldier(player_team, w // 2 - 3, y0,     RIFLE,  6, 100, player_fg)
        spawn_soldier(player_team, w // 2,     y0 + 1, SMG,   10, 100, player_fg)
        spawn_soldier(player_team, w // 2 + 3, y0,     SNIPER, 4, 100, player_fg)

        # --- OPTIONAL: spawn defenders in the same starting cell (old behavior) ---
        # If you keep this enabled, your "spawn enemies on entering new area" should
        # detect already-present enemies and not double-spawn.
        spawn_enemy_team_on_start = False
        if spawn_enemy_team_on_start:
            enemy_team = 1 - player_team
            enemy_fg = (255, 180, 120) if enemy_team == 1 else (120, 180, 255)

            spawn_soldier(enemy_team, w // 2 - 3, 3, RIFLE,  6, 100, enemy_fg)
            spawn_soldier(enemy_team, w // 2,     2, SMG,   10, 100, enemy_fg)
            spawn_soldier(enemy_team, w // 2 + 3, 4, SNIPER, 4, 100, enemy_fg)

        self.team_ap[0] = self.team_ap_max
        self.team_ap[1] = self.team_ap_max

        self._clamp_selection()
        sel = self.get_selected_actor()
        if sel:
            self.aim_x, self.aim_y = sel.x, sel.y

        self.log.add(
            "Controls: Arrows move | Tab cycle | F aim/fire | R reload | G pickup | "
            "Space end turn | C character sheet | Esc quit"
        )

        self.eating_names = [
            "eat", "devour", "binge on", "feast on", "wolf down", "shovel in",
            "choke on", "suck on", "nom on", "gorge on", "snarf down", "inhale", "scarf down"
        ]
        self.eating_name = ""

        # Optional: spawn enemies for this cell once at the start
        # (if you want the starting cell to have enemies)
        self._spawn_enemies_for_current_cell()

        self.log.add(f"Spawned player squad in cell ({self.gx},{self.gy}).")

    def _make_starting_inventory(self) -> list:
        # Keep enemies simpler or same as player, up to you:
        return [
            Bandage(name="Bandage", ch=ord("#"), fg=(245, 245, 221), stackable=True, qty=1, power=3),
            IronSupplement(name="Iron Supplement", ch=ord("!"), fg=(255, 255, 255), stackable=True, qty=3, regen=2, duration=12),
        ]

    def _spawn_enemies_for_current_cell(self) -> None:
        cell = (self.gx, self.gy)
        if cell in self.spawned_enemy_cells:
            return

        enemy_team = 0

        # If already present in THIS cell, mark and exit
        if any(a.alive and a.team_id == enemy_team and a.gx == self.gx and a.gy == self.gy for a in self.actors):
            self.spawned_enemy_cells.add(cell)
            return

        # Collect friendly positions in this cell (so we don't spawn on top / too close)
        friendly_team = 1 - enemy_team
        friendlies = [
            (a.x, a.y)
            for a in self.actors
            if a.alive and a.team_id == friendly_team and a.gx == self.gx and a.gy == self.gy
        ]

        def too_close_to_friendlies(x: int, y: int, min_dist: int = 6) -> bool:
            for fx, fy in friendlies:
                if abs(fx - x) + abs(fy - y) < min_dist:
                    return True
            return False

        n = random.randint(3, 6)
        weapons = [RIFLE, SMG, SNIPER]

        # spawn band depends on biome row (optional flavor)
        # NOTE: you use gy==0 streets, gy==1 forest, else beach.
        if self.gy == 0:  # streets (top row)
            y_min, y_max = self.game_map.h - 8, self.game_map.h - 2
        elif self.gy == 1:  # forest (middle row)
            y_min, y_max = self.game_map.h // 3, (self.game_map.h * 2) // 3
        else:  # beach (bottom row)
            y_min, y_max = 1, 8

        spawned = 0
        tries = 800

        while spawned < n and tries > 0:
            tries -= 1
            x = random.randint(0, self.game_map.w - 1)
            y = random.randint(max(0, y_min), min(self.game_map.h - 1, y_max))

            if not self.game_map.is_walkable(x, y):
                continue

            if self.actor_at(x, y) is not None:
                continue

            # Don't spawn too close to friendlies (if any exist in this cell)
            if friendlies and too_close_to_friendlies(x, y, min_dist=6):
                continue

            weapon = random.choice(weapons)
            rand_data = generate_random_soldier_info()
            inv = self._make_starting_inventory()

            enemy = Actor(
                enemy_team,
                x,
                y,
                ord("☻"),
                (120, 180, 255),
                10,
                10,
                weapon,
                weapon.mag_size,
                100,
                inventory=inv,
                **rand_data,
            )
            enemy.gx, enemy.gy = self.gx, self.gy
            self.actors.append(enemy)
            spawned += 1

        self.spawned_enemy_cells.add(cell)

        if spawned > 0:
            self.log.add(f"Enemy squad enters the area! (+{spawned})")
        else:
            self.log.add("Area seems quiet... (no valid spawn points)")

    def alive_actors(self) -> List[Actor]:
        return [a for a in self.actors if a.alive and a.gx == self.gx and a.gy == self.gy]

    def team_actors(self, team_id: int) -> List[Actor]:
        return [a for a in self.actors if a.alive and a.team_id == team_id and a.gx == self.gx and a.gy == self.gy]

    def enemy_actors(self, team_id: int) -> List[Actor]:
        return [a for a in self.actors if a.alive and a.team_id != team_id and a.gx == self.gx and a.gy == self.gy]

    def actor_at(self, x: int, y: int) -> Optional[Actor]:
        for a in self.alive_actors():
            if a.x == x and a.y == y:
                return a
        return None

    def crate_at(self, x: int, y: int) -> Optional[Crate]:
        for it in self.crates:
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
            print("sssss")
            hit_part = imp.actor.take_hit(imp.damage, imp.acc)
            self.log.add(
                f"{imp.shooter_obj.get_short_name()} hits {imp.actor.get_short_name()} ({hit_part.name}) "
                f"Trauma {imp.damage}, bleed {imp.actor.bleed_rate}/turn."
            )
            friendly_fire = imp.shooter_obj.team_id == imp.actor.team_id
            if friendly_fire:
                self.log.add(f"Friendly fire from {imp.actor.get_short_name()}! Idiot!")

            if not imp.actor.alive:
                self.log.add(f"{imp.actor.get_short_name()} is down!")
                if not friendly_fire:
                    self._check_victory()
                else:
                    insults = ["Fucking cretin!", "Bro wtf", "Open your fucking eyes maybe??", "What the fuck, it was his birthday!"]
                    self.log.add(f"{random.choice(insults)}")

            self._spawn_blood_spurt(
                sx=imp.shooter_obj.x,
                sy=imp.shooter_obj.y,
                vx=imp.actor.x,
                vy=imp.actor.y,
                power=max(3, imp.damage * 2)
            )
            return

        if imp.impact_type == "tile" and imp.tile_xy:
            x, y = imp.tile_xy
            if self.game_map.tile_at(x, y) == DOOR:
                self.game_map.set_tile(x, y, SAND)
                self.log.add(f"{imp.shooter_obj.get_short_name()} blows open the door!")
            else:
                self.log.add(f"{imp.shooter_obj.get_short_name()} hits {self.game_map.tile_at(x,y).name}.")
            return

        self.log.add(f"{imp.shooter_obj.get_short_name()} fires.")

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

    def _handle_sheet_keydown(self, ev: tcod.event.KeyDown) -> None:
        if ev.sym == tcod.event.KeySym.ESCAPE:
            self.ui_mode = UIState.PLAY
            return
        # scrolling
        if ev.sym == tcod.event.KeySym.UP:
            self.sheet_scroll = max(0, self.sheet_scroll - 1)
        elif ev.sym == tcod.event.KeySym.DOWN:
            self.sheet_scroll += 1
        elif ev.sym == tcod.event.KeySym.PAGEUP:
            self.sheet_scroll = max(0, self.sheet_scroll - 10)
        elif ev.sym == tcod.event.KeySym.PAGEDOWN:
            self.sheet_scroll += 10
        # maybe render everything onto one tab

    def _handle_inventory_keydown(self, ev: tcod.event.KeyDown) -> None:
        sel = self.get_selected_actor()
        if not sel:
            self.ui_mode = UIState.PLAY
            return

        inv = getattr(sel, "inventory", [])
        if ev.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.i):
            self.ui_mode = UIState.PLAY
            return

        if ev.sym == tcod.event.KeySym.UP:
            if inv:
                self.inv_index = (self.inv_index - 1) % len(inv)
            return
        if ev.sym == tcod.event.KeySym.DOWN:
            if inv:
                self.inv_index = (self.inv_index + 1) % len(inv)
            return

        if ev.sym == tcod.event.KeySym.RETURN:
            print(inv)
            if not inv:
                return
            it = inv[self.inv_index]
            print(it)
            # block usage during bullet animation is already handled in your early return

            # Spend AP to use item (tune cost)
            USE_COST = 2
            if not self._spend_ap(USE_COST):
                return

            consumed = it.use(self, sel)  # Engine acts as ctx (add log_add + spawn_explosion methods below)
            print(f"Is consumed: {consumed}")
            if consumed:
                # stackables
                if getattr(it, "stackable", False) and it.qty > 1:
                    it.qty -= 1
                else:
                    inv.pop(self.inv_index)
                    self.inv_index = max(0, min(self.inv_index, len(inv) - 1))
            return

        if ev.sym == tcod.event.KeySym.d:
            # Drop item onto ground at player's tile
            if not inv:
                return
            DROP_COST = 1
            if not self._spend_ap(DROP_COST):
                return
            it = inv.pop(self.inv_index)
            # You already have Item instances with x,y for map items; if your inventory items
            # don't have x,y, create a "world item" wrapper or just add attributes:
            it.x, it.y = sel.x, sel.y
            self.items.append(it)
            self.log.add(f"{sel.get_short_name()} drops {it.name}.")
            self.inv_index = max(0, min(self.inv_index, len(inv) - 1))
            return

    def _handle_keydown(self, ev: tcod.event.KeyDown) -> None:

        if self.is_bullet_animation_active():
            return

        # Later: if ANY animation is active, ignore the input
        # besides blinking status animations.

        if self.ui_mode == UIState.CHAR_SHEET:
            self._handle_sheet_keydown(ev)
            return

        if self.ui_mode == UIState.INVENTORY:
            self._handle_inventory_keydown(ev)
            return

        if ev.sym == tcod.event.KeySym.ESCAPE:
            if self.ui_mode == UIState.CHAR_SHEET:
                self.ui_mode = UIState.PLAY
                return
            if self.aiming:
                self.aiming = False
                self.log.add("Aiming cancelled.")
            else:
                self.running = False
            return

        if ev.sym == tcod.event.KeySym.TAB:
            print(self.get_selected_actor().blood)
            self._cycle_selected(+1)
            return

        if ev.sym == tcod.event.KeySym.SPACE:
            self.end_turn()
            return

        if ev.sym == tcod.event.KeySym.O:
            self.try_open_door()
            return

        if ev.sym == tcod.event.KeySym.C:
            if self.get_selected_actor():
                self.eating_name = random.choice(self.eating_names)
                self.ui_mode = UIState.CHAR_SHEET
                self.sheet_tab = SheetTab.OVERVIEW
                self.sheet_scroll = 0
            return

        if ev.sym == tcod.event.KeySym.I:
            if self.get_selected_actor():
                self.ui_mode = UIState.INVENTORY
                self.inv_index = 0
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

    def _tick_team_bleeding(self, team_id: int) -> None:
        deaths = []

        for a in self.team_actors(team_id):
            if not a.alive:
                continue

            loss = a.tick_bleeding()
            if loss > 0 and not a.alive:
                deaths.append(a.get_short_name())

        for name in deaths:
            self.log.add(f"{name} bleeds out!")

    def _tick_team_blood_regen(self, team_id: int) -> None:
        for a in self.team_actors(team_id):
            if not a.alive:
                continue
            a.tick_blood_regen()

    def end_turn(self) -> None:
        # for a in self.alive_actors():
        #     loss = a.tick_bleeding()
        #     if loss > 0:
        #         self.log.add(f"{a.get_short_name()} loses {loss} blood!")
        #         if not a.alive:
        #             self.log.add(f"{a.get_short_name()} bleeds out!")

        self.aiming = False
        self.current_team = 1 - self.current_team
        self.team_ap[self.current_team] = self.team_ap_max
        self._clamp_selection()

        self.turn_count += 1

        # TODO: Add summary of damage of the last turn, e.g. "Def-2 took 3 damage, Atk-1 took 4 damage"

        # Spawn crates at end of a full round (both teams took turns) -> approximate by every N turns
        if self.turn_count % self.crate_every_n_turns == 0:
            self.spawn_random_crate()

        self._check_victory()

    def _spend_ap(self, cost: int) -> bool: # every action results in this
        if self.team_ap[self.current_team] < cost:
            self.log.add("Not enough AP.")
            return False

        # ticks TODO|: for every cost?
        # self._tick_team_bleeding(0)
        # self._tick_team_bleeding(1)
        # self._tick_team_blood_regen(0)
        # self._tick_team_blood_regen(1)

        self.team_ap[self.current_team] -= cost

        self._tick_world_on_action(cost)

        return True

    def _tick_world_on_action(self, ap_spent: int) -> None:
        deaths = []

        for a in self.alive_actors():
            if not a.alive:
                continue

            band_loss = a.tick_bandages(ap_spent)

            bleed_loss = a.tick_bleeding()

            regen = a.tick_blood_regen()

            if not a.alive:
                deaths.append(a.get_short_name())

        for name in deaths:
            self.log.add(f"{name} bleeds out!")

        self._check_victory()

    def try_move_selected(self, dx: int, dy: int) -> None:
        sel = self.get_selected_actor()
        if not sel or not sel.alive:
            self.log.add("No soldier selected.")
            return
        nx, ny = sel.x + dx, sel.y + dy

        # --- map edge transitions ---
        if nx < 0:
            if not self.try_change_map(-1, 0):
                return
            sel.x = self.game_map.w - 1
            sel.y = max(0, min(self.game_map.h - 1, ny))
            self.aim_x, self.aim_y = sel.x, sel.y
            sel.gx, sel.gy = self.gx, self.gy
            return

        if nx >= self.game_map.w:
            if not self.try_change_map(+1, 0):
                return
            sel.x = 0
            sel.y = max(0, min(self.game_map.h - 1, ny))
            self.aim_x, self.aim_y = sel.x, sel.y
            sel.gx, sel.gy = self.gx, self.gy
            return

        if ny < 0:
            if not self.try_change_map(0, -1):
                return
            sel.y = self.game_map.h - 1
            sel.x = max(0, min(self.game_map.w - 1, nx))
            self.aim_x, self.aim_y = sel.x, sel.y
            sel.gx, sel.gy = self.gx, self.gy
            return

        if ny >= self.game_map.h:
            if not self.try_change_map(0, +1):
                return
            sel.y = 0
            sel.x = max(0, min(self.game_map.w - 1, nx))
            self.aim_x, self.aim_y = sel.x, sel.y
            sel.gx, sel.gy = self.gx, self.gy
            return

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
                self.log.add(f"{sel.get_short_name()} opens the door.")
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
        self.log.add(f"{sel.get_short_name()} reloads (+{loaded}).")

    def try_pickup(self) -> None:
        sel = self.get_selected_actor()
        if not sel or not sel.alive:
            return
        it = self.crate_at(sel.x, sel.y)
        if not it:
            self.log.add("Nothing to pick up.")
            return
        if not self._spend_ap(self.PICKUP_COST):
            return

        # if crate
        if it.kind == "ammo":
            sel.ammo_reserve += it.amount
            self.log.add(f"{sel.get_short_name()} picks up ammo (+{it.amount}).")
        elif it.kind == "med":
            before = sel.hp
            sel.hp = min(sel.hp_max, sel.hp + it.amount)
            self.log.add(f"{sel.get_short_name()} uses medkit (+{sel.hp - before} HP).")

        self.crates.remove(it)

    def miss_offset_by_acc_(self, acc: int) -> int:
        # If roll >= acc, so offset decreases with accuracy increase
        # To hit, you need to roll < acc
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

    def compute_spread_acc(self, shooter: Actor, dist: int) -> int:
        acc = shooter.weapon.base_accuracy
        if dist > 5:
            acc -= 2 * (dist - 5)
        return clamp(acc, 5, 95)

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
        if not self.game_map.los(shooter.x, shooter.y, tx, ty):
            self.log.add("No line of sight.")
            return

        acc = self.compute_spread_acc(shooter, dist)
        if target: # TODO: Reflect this in status!
            acc -= self.game_map.cover_bonus_at(target.x, target.y)

        to_hit_roll = random.randint(1, 100)
        acc = clamp(acc, 5, 95)
        is_hit = to_hit_roll <= acc

        print(f"acc: {acc}, roll: {to_hit_roll}, is_hit: {is_hit}")

        bx, by = tx, ty
        if not is_hit:
            # offset the bullet path (tx,ty) taking accuracy into account when the roll <= acc
            bx, by = self.pick_miss_endpoint(shooter.x, shooter.y, tx, ty, acc, self.game_map.w, self.game_map.h)
            self.log.add(f"{shooter.get_short_name()}'s hand shakes!")

        line = tcod.los.bresenham((shooter.x, shooter.y), (bx, by)).tolist()
        path: List[Tuple[int, int]] = []

        impact_actor: Optional[Actor] = None
        impact_tile: Optional[Tuple[int, int]] = None

        for x, y in line[1:]:
            x, y = int(x), int(y)
            path.append((x, y))

            if self.game_map.blocks_los(x, y):
                impact_tile = (x, y)
                break

            a = self.actor_at(x, y)
            if a and a.alive:
                if is_hit:
                    impact_actor = a # if direct hit
                    break
                acc -= self.game_map.cover_bonus_at(x, y)  # cover affects any victim, not just the intended target
                acc = clamp(acc, 5, 95)

                roll = random.randint(1, 100)
                if roll <= acc:
                    impact_actor = a
                break

        self.bullet_path = path
        self.bullet_index = 0
        self.bullet_timer = 0.0

        if impact_actor is not None:
            self.pending_impact = PendingImpact(
                impact_type="actor",
                actor=impact_actor,
                tile_xy=None,
                shooter_obj=shooter,
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
                shooter_obj=shooter,
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
                shooter_obj=shooter,
                damage=0,
                acc=acc,
                roll=to_hit_roll,
                is_hit_roll=is_hit
            )

    # ----------------- Crates -----------------
    def spawn_random_crate(self) -> None:
        attempts = 200
        for _ in range(attempts):
            x = random.randint(0, self.game_map.w - 1)
            y = random.randint(self.game_map.h // 4, (self.game_map.h * 3) // 4)
            if not self.game_map.is_walkable(x, y):
                continue
            if self.actor_at(x, y) is not None:
                continue
            if self.crate_at(x, y) is not None:
                continue

            if random.random() < 0.5:
                it = Crate.ammo_crate(x, y, amount=random.choice([6, 8, 10]))
            else:
                it = Crate.med_crate(x, y, amount=random.choice([3, 4, 5]))
            self.crates.append(it)
            self.log.add(f"A crate drops at ({x},{y})!")
            return

    def render(self, con: tcod.Console) -> None:
        self._render_map(con)
        self._render_soldiers_panel(con)
        self._render_equip_panel(con)
        self._render_log_panel(con)

        if self.ui_mode == UIState.CHAR_SHEET:
            self._render_character_sheet(con)

        if self.ui_mode == UIState.INVENTORY:
            self._render_inventory(con)

    def _render_map(self, con: tcod.Console) -> None:
        r = self.layout.map_rect

        # draw tiles
        for y in range(self.game_map.h):
            for x in range(self.game_map.w):
                t = self.game_map.tile_at(x, y)
                if (self.game_map.blood[y][x] > 0):
                    # blood overlay: red tint with intensity based on blood level
                    blood_level = self.game_map.blood[y][x]
                    intensity = min(150, blood_level * 15)  # cap intensity to avoid too dark
                    _r, _g, _b = t.fg
                    _r = min(255, _r + intensity)
                    _g = max(0, _g - intensity)
                    _b = max(0, _b - intensity)
                    con.print(x=r.x + x, y=r.y + y, string=chr(t.ch), fg=(_r, _g, _b), bg=(90, 0, 0))
                else:
                    con.print(x=r.x + x, y=r.y + y, string=chr(t.ch), fg=t.fg, bg=t.bg)

        for it in self.crates:
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
        con.print(r.x + 22, r.y + 0, f"Turn: {self.turn_count}", fg=(220, 220, 220))

    def _spawn_blood_spurt(self, sx: int, sy: int, vx: int, vy: int, power: int = 5) -> None:
        dx = vx - sx
        dy = vy - sy

        # Normalize direction to a grid step (-1,0,1)
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        # If shot is perfectly aligned weirdly, still ensure movement
        if step_x == 0 and step_y == 0:
            return

        # Spray length depends on power; add some randomness
        length = max(2, min(10, power + random.randint(-1, 2)))

        # Start at victim, go forward
        x, y = vx, vy
        self.game_map.add_blood(vx, vy, amount=2)
        for i in range(length):
            x += step_x
            y += step_y

            if not self.game_map.tile_at(x, y).walkable:
                return
            # if self.game_map.tile_at(x, y) == DOOR or self.game_map.tile_at(x, y) == ROCK or self.game_map.tile_at(x, y) == TREE:
            #     return

            if not (0 <= x < self.game_map.w and 0 <= y < self.game_map.h):
                break

            # stop if hits a wall (blood splats there)
            if self.game_map.blocks_los(x, y):
                self.game_map.add_blood(x, y, amount=3)
                break

            # jitter: blood isn't a laser line
            jx = x + random.randint(-1, 1) if random.random() < 0.35 else x
            jy = y + random.randint(-1, 1) if random.random() < 0.35 else y

            self.game_map.add_blood(jx, jy, amount=1)

        # Extra splat at victim position
    def spawn_explosion(self, x: int, y: int, radius: int, damage: int, source_team: int) -> None:
        # Affect actors in diamond radius (Manhattan). Keep it simple.
        for a in self.alive_actors():
            dist = abs(a.x - x) + abs(a.y - y)
            if dist <= radius:
                # optional cover reduction later
                a.take_damage(damage)  # or take_hit/blood logic
                self.log.add(f"{a.get_short_name()} is hit by explosion ({damage}).")
        # TODO: shrapnel, animation etc...

    def draw_section_divider(self, con, x, y, width, title, fg=(180,180,180), bg=(0,0,0)):
        line_chr = '═'
        text = f" {title} "
        remaining = width - len(text)-1
        left = 1 + remaining // 2
        right = remaining - left - 1
        line = line_chr * left + text + line_chr * right
        con.print(x+1, y, line[:width], fg=fg, bg=bg)

    def _panel_frame(self, con: tcod.Console, x: int, y: int, w: int, h: int, title: str) -> None:
        fg = (160, 160, 160)
        bg = (0, 0, 0)
        con.draw_frame(x, y, w, h, clear=False, fg=fg, bg=bg)
        con.print_box(x + 2, y, w - 4, 1, f" {title} ", fg=fg, bg=bg)

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
                    f"{a.get_short_name():6} HP {a.hp:2}/{a.hp_max:2}",
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

        con.print(r.x + 1, r.y + 2, f"{sel.get_short_name()} ({'ATK' if sel.team_id==1 else 'DEF'})", fg=(255, 255, 255))
        con.print(r.x + 1, r.y + 3, f"Pos: ({sel.x},{sel.y})", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 4, f"Weapon: {sel.weapon.name}", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 5, f"Range {sel.weapon.range}  Acc {sel.weapon.base_accuracy}%", fg=(200, 200, 200))
        con.print(r.x + 1, r.y + 6, f"Dmg {sel.weapon.damage}  Ammo {sel.ammo_in_mag}/{sel.weapon.mag_size} +{sel.ammo_reserve}", fg=(200, 200, 200))

        it = self.crate_at(sel.x, sel.y)
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

    def _render_character_sheet(self, con: tcod.Console) -> None:
        sel = self.get_selected_actor()
        if not sel:
            return

        x, y = 1, 2
        w, h = self.layout.screen_w - 2, self.layout.screen_h - 2

        fg = (220, 220, 220)
        dim = (40, 40, 40)
        bg = (0, 0, 0)

        con.draw_rect(0, 0, self.layout.screen_w, self.layout.screen_h, ch=ord(' '), bg=dim, bg_blend=tcod.BKGND_MULTIPLY)

        header = f" {sel.name} ({'ATK' if sel.team_id==1 else 'DEF'})  |  ESC/C: close"
        con.print(x + 2, y+1, header[: w - 4], fg=(255, 215, 0), bg=bg)
        self._panel_frame(con, x, y, w, h, "Character Sheet")

        inner_x = x + 1
        inner_y = y + 2
        inner_w = w - 2
        inner_h = h - 3

        gap = 1
        left_w = int(inner_w * 0.62)
        right_w = inner_w - left_w - gap

        left_x = inner_x
        right_x = inner_x + left_w + gap

        desc_h = int(inner_h * 0.55)
        equip_h = inner_h - desc_h - gap

        desc_x, desc_y, desc_w = left_x, inner_y, left_w
        equip_x, equip_y, equip_w = left_x, inner_y + desc_h + gap, left_w

        attr_h = max(6, int(inner_h * 0.24))
        status_h = inner_h - attr_h

        attr_x, attr_y, attr_w = right_x, inner_y, right_w
        status_x, status_y, status_w = right_x, attr_h + gap + 3, right_w

        self._panel_frame(con, desc_x, desc_y, desc_w, desc_h, "Description")
        self._panel_frame(con, equip_x, equip_y, equip_w, equip_h, "Equipment")

        self._panel_frame(con, attr_x, attr_y, attr_w, attr_h, "Attributes")
        self._panel_frame(con, status_x, status_y, status_w, status_h, "Status")

        self.draw_section_divider(con, status_x, status_y + status_h//2 - 4, status_w, "Body")

        paperdoll_head = sel.body_parts[0]
        paperdoll_neck = sel.body_parts[1]
        paperdoll_torso = sel.body_parts[2]
        paperdoll_left_arm = sel.body_parts[3]
        paperdoll_right_arm = sel.body_parts[4]
        paperdoll_left_hand = sel.body_parts[5]
        paperdoll_right_hand = sel.body_parts[6]
        paperdoll_left_leg = sel.body_parts[7]
        paperdoll_right_leg = sel.body_parts[8]
        paperdoll_left_foot = sel.body_parts[9]
        paperdoll_right_foot = sel.body_parts[10]

        paperdoll_y = (status_y + status_h//2 - 3) + 3

        status = sel.get_body_part_status_and_color("head")
        con.print(status_x + status_w//2, paperdoll_y, f"{paperdoll_head.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("neck")
        con.print(status_x + status_w//2, paperdoll_y + 1, f"{paperdoll_neck.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("left arm")
        con.print(status_x + status_w//2 - 1, paperdoll_y + 2, f"{paperdoll_left_arm.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("right arm")
        con.print(status_x + status_w//2 + 1, paperdoll_y + 2, f"{paperdoll_right_arm.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("torso")
        con.print(status_x + status_w//2, paperdoll_y + 3, f"{paperdoll_torso.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("left hand")
        con.print(status_x + status_w//2 - 2, paperdoll_y + 2, f"{paperdoll_left_hand.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("right hand")
        con.print(status_x + status_w//2 + 2, paperdoll_y + 2, f"{paperdoll_right_hand.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("left leg")
        con.print(status_x + status_w//2 - 1, paperdoll_y + 5, f"{paperdoll_left_leg.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("right leg")
        con.print(status_x + status_w//2 + 1, paperdoll_y + 5, f"{paperdoll_right_leg.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("left foot")
        con.print(status_x + status_w//2 - 2, paperdoll_y + 6, f"{paperdoll_left_foot.char}", fg=status[1], bg=bg)
        status = sel.get_body_part_status_and_color("right foot")
        con.print(status_x + status_w//2 + 2, paperdoll_y + 6, f"{paperdoll_right_foot.char}", fg=status[1], bg=bg)

        description = "Priv. " + sel.rank + " " + sel.name + " is proudly: " + sel.nationality + ".\n"
        description += "They like to " + self.eating_name + " " + sel.favorite_dish + ".\n"
        description += "They know that " + sel.worldview + " is the way to go, and they have this view since graduating from " + sel.university + ".\n"
        description += "They think that " + sel.favorite_sentence.lower() + ".\n"
        description += "When the war ends, they want to go back to the regular life being a " + sel.occupation + "."

        desc_lines = textwrap.wrap(description, desc_w - 2)
        ty = desc_y + 1
        for line in desc_lines[: desc_h - 2]:
            con.print(desc_x + 1, ty, line, fg=fg, bg=bg)
            ty += 1

        armor = getattr(sel, "armor", None)

        STR = getattr(sel, "str", getattr(sel, "strength", 0))
        DEX = getattr(sel, "dex", getattr(sel, "dexterity", 0))
        CON = getattr(sel, "con", getattr(sel, "constitution", 0))

        con.print(attr_x + 1, attr_y + 1, f"STR: {STR}", fg=fg, bg=bg)
        con.print(attr_x + 1, attr_y + 2, f"DEX: {DEX}", fg=fg, bg=bg)
        con.print(attr_x + 1, attr_y + 3, f"CON: {CON}", fg=fg, bg=bg)

        dex_bonus = getattr(sel, "dex_bonus", 0)
        if attr_h >= 6:
            con.print(attr_x + 1, attr_y + 5, f"Dex bonus: {dex_bonus}", fg=(180, 180, 180), bg=bg)

        health_x = status_x
        health_y = status_y + 1
        health_w = right_w

        bar_w = max(2, health_w - 10)
        filled = 0 if sel.blood <= 0 else int((sel.blood / sel.blood_max) * bar_w)
        filled = max(0, min(bar_w, filled))
        con.draw_rect(x=health_x+1, y=health_y + 1, width=bar_w, height=1, ch=1, bg=(70, 0, 0))
        con.draw_rect(x=health_x+1, y=health_y + 1, width=filled, height=1, ch=1, bg=(245, 0, 0))
        con.print(health_x + 1, health_y + 1, f"Blood: {sel.blood}/{sel.blood_max}", fg=fg, bg=(245, 0, 0))
        statuses = []
        statuses.append(sel.get_bleeding_status_and_color())
        statuses.append(sel.get_treatment_status_and_color())
        statuses.append(sel.get_iron_supplement_status_and_color())
        con.print(status_x + 1, status_y + 3, statuses[0][0][:status_w-2], fg=statuses[0][1], bg=statuses[0][2])
        con.print(status_x + 1, status_y + 4, statuses[1][0][:status_w-2], fg=statuses[1][1], bg=statuses[1][2])
        if statuses[2][0] is not None:
            con.print(status_x + 1, status_y + 5, statuses[2][0][:status_w-2], fg=statuses[2][1], bg=statuses[2][2])

        con.print(equip_x + 1, equip_y + 1, f"Weapon: {sel.weapon.name}", fg=fg, bg=bg)
        con.print(
            equip_x + 1,
            equip_y + 2,
            f"Ammo: {sel.ammo_in_mag}/{sel.weapon.mag_size} +{sel.ammo_reserve}",
            fg=fg,
            bg=bg,
        )

        eq = getattr(sel, "equipment", {})
        inv = getattr(sel, "inventory", [])

        slot_y = equip_y + 4
        if eq and equip_h >= 10:
            con.print(equip_x + 1, slot_y, "Slots:", fg=(180, 180, 180), bg=bg)
            slot_y += 1
            for slot in ["head", "body", "hands", "legs"]:
                val = eq.get(slot, None)
                name = getattr(val, "name", str(val)) if val else "(empty)"
                con.print(equip_x + 1, slot_y, f"{slot:>5}: {name}"[: equip_w - 2], fg=fg, bg=bg)
                slot_y += 1

        inv_title_y = max(slot_y + 1, equip_y + 8)
        if inv_title_y < equip_y + equip_h - 1:
            con.print(equip_x + 1, inv_title_y, "Inventory:", fg=(180, 180, 180), bg=bg)
            ty = inv_title_y + 1
            if not inv:
                con.print(equip_x + 1, ty, "(empty)", fg=(140, 140, 140), bg=bg)
            else:
                top = ty + 3
                max_rows = h - 5
                start = 0
                if self.inv_index >= max_rows:
                    start = self.inv_index - max_rows + 1
                for row, idx in enumerate(range(start, min(len(inv), start + max_rows))):
                    it = inv[idx]
                    marker = ">" if idx == self.inv_index else " "
                    qty = f" x{it.qty}" if getattr(it, "stackable", False) and it.qty > 1 else ""
                    con.print(equip_x + 1, top + row, f"{marker} {it.name}{qty}", fg=(220,220,220))

    def _render_inventory(self, con: tcod.Console) -> None:
        sel = self.get_selected_actor()
        if not sel:
            return

        # darken background
        con.draw_rect(0, 0, self.layout.screen_w, self.layout.screen_h,
                    ch=ord(" "), bg=(40,40,40), bg_blend=tcod.BKGND_MULTIPLY)

        w, h = self.layout.screen_w - 10, self.layout.screen_h - 10
        x, y = 5, 5
        self._panel_frame(con, x, y, w, h, "Inventory")

        inv = getattr(sel, "inventory", [])
        con.print(x + 2, y + 1, f"{sel.get_short_name()}  |  Enter: use  D: drop  Esc/I: close", fg=(220,220,220))

        if not inv:
            con.print(x + 2, y + 3, "(empty)", fg=(140,140,140))
            return

        top = y + 3
        max_rows = h - 5
        start = 0
        if self.inv_index >= max_rows:
            start = self.inv_index - max_rows + 1

        for row, idx in enumerate(range(start, min(len(inv), start + max_rows))):
            it = inv[idx]
            marker = ">" if idx == self.inv_index else " "
            qty = f" x{it.qty}" if getattr(it, "stackable", False) and it.qty > 1 else ""
            con.print(x + 2, top + row, f"{marker} {it.name}{qty}", fg=(220,220,220))

    def log_add(self, msg: str) -> None:
        self.log.add(msg)