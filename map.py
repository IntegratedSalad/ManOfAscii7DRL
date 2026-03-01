from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
import random

from item import Item

import tcod

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Tile:
    ch: int
    fg: Color
    bg: Color
    walkable: bool
    transparent: bool
    name: str


OCEAN = Tile(ord("~"), (30, 80, 120), (5, 10, 20), False, True, "Ocean")
SAND = Tile(ord("."), (120, 110, 60), (10, 10, 10), True, True, "Sand")
GRASS = Tile(ord(","), (40, 120, 60), (8, 10, 8), True, True, "Grass")
UPPER = Tile(ord(";"), (70, 140, 80), (8, 10, 8), True, True, "Upper Grass")
TREE = Tile(ord("T"), (0, 160, 0), (8, 10, 8), False, False, "Tree")
ROCK = Tile(ord("O"), (120, 120, 120), (10, 10, 10), False, False, "Rock")
CONCRETE = Tile(ord("#"), (100, 100, 100), (10, 10, 10), False, False, "Concrete")
DOOR = Tile(ord("+"), (200, 180, 120), (10, 10, 10), False, False, "Door")


@dataclass
class GameMap:
    w: int
    h: int
    tiles: List[List[Tile]]

    # For fast LOS / FOV:
    transparent: List[List[bool]]
    walkable: List[List[bool]]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def tile_at(self, x: int, y: int) -> Tile:
        return self.tiles[y][x]

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.walkable[y][x]

    def blocks_los(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and (not self.transparent[y][x])

    def set_tile(self, x: int, y: int, tile: Tile) -> None:
        self.tiles[y][x] = tile
        self.walkable[y][x] = tile.walkable
        self.transparent[y][x] = tile.transparent

    @staticmethod
    def generate_beach(w: int, h: int) -> "GameMap":
        # Horizontal bands from bottom to top:
        # ocean -> sand -> grass -> upper grass w/ rocks
        tiles: List[List[Tile]] = [[GRASS for _ in range(w)] for _ in range(h)]

        ocean_h = max(4, h // 6)
        sand_h = max(4, h // 8)
        grass_h = max(6, h // 5)
        # remainder is upper

        for y in range(h):
            if y >= h - ocean_h:
                row_tile = OCEAN
            elif y >= h - ocean_h - sand_h:
                row_tile = SAND
            elif y >= h - ocean_h - sand_h - grass_h:
                row_tile = GRASS
            else:
                row_tile = UPPER

            for x in range(w):
                tiles[y][x] = row_tile

        transparent = [[tiles[y][x].transparent for x in range(w)] for y in range(h)]
        walkable = [[tiles[y][x].walkable for x in range(w)] for y in range(h)]
        gm = GameMap(w=w, h=h, tiles=tiles, transparent=transparent, walkable=walkable)

        # Add rocks only on upper layer (top chunk)
        upper_limit = h - ocean_h - sand_h - grass_h
        rock_count = (w * max(1, upper_limit)) // 25  # tune density
        rng = random.Random()

        for _ in range(rock_count):
            x = rng.randrange(0, w)
            y = rng.randrange(0, max(1, upper_limit))
            # avoid making totally clogged areas: place rock if neighbors not too many rocks
            if gm.tile_at(x, y) == UPPER and rng.random() < 0.85:
                gm.set_tile(x, y, ROCK)

        return gm

    @staticmethod
    def generate_forest(w: int, h: int) -> "GameMap":
        tiles: List[List[Tile]] = [[UPPER for _ in range(w)] for _ in range(h)]

        transparent = [[tiles[y][x].transparent for x in range(w)] for y in range(h)]
        walkable = [[tiles[y][x].walkable for x in range(w)] for y in range(h)]
        gm = GameMap(w=w, h=h, tiles=tiles, transparent=transparent, walkable=walkable)

        rng = random.Random()

        tree_count = (w * h) // 5  # roughly one tree per five cells
        for _ in range(tree_count):
            x = rng.randrange(0, w)
            y = rng.randrange(0, h)
            if gm.tile_at(x, y) == UPPER and rng.random() < 0.8:
                gm.set_tile(x, y, TREE)

        rock_count = (w * h) // 50
        for _ in range(rock_count):
            x = rng.randrange(0, w)
            y = rng.randrange(0, h)
            if gm.tile_at(x, y) == UPPER and rng.random() < 0.7:
                gm.set_tile(x, y, ROCK)

        return gm

    @staticmethod
    def generate_streets(w: int, h: int) -> tuple["GameMap", List["Item"]]:
        tiles: List[List[Tile]] = [[SAND for _ in range(w)] for _ in range(h)]

        transparent = [[tiles[y][x].transparent for x in range(w)] for y in range(h)]
        walkable = [[tiles[y][x].walkable for x in range(w)] for y in range(h)]
        gm = GameMap(w=w, h=h, tiles=tiles, transparent=transparent, walkable=walkable)

        rng = random.Random()
        starting_items: List[Item] = []

        building_count = max(1, (w * h) // 300)
        for _ in range(building_count):
            bw = rng.randint(4, 8)
            bh = rng.randint(4, 8)
            bx = rng.randint(1, w - bw - 2)
            by = rng.randint(1, h - bh - 2)

            for x in range(bx, bx + bw):
                gm.set_tile(x, by, CONCRETE)
                gm.set_tile(x, by + bh - 1, CONCRETE)
            for y in range(by, by + bh):
                gm.set_tile(bx, y, CONCRETE)
                gm.set_tile(bx + bw - 1, y, CONCRETE)

            # one door on a random side
            side = rng.choice(["north", "south", "east", "west"])
            if side == "north":
                dx = rng.randint(bx + 1, bx + bw - 2)
                dy = by
            elif side == "south":
                dx = rng.randint(bx + 1, bx + bw - 2)
                dy = by + bh - 1
            elif side == "east":
                dx = bx + bw - 1
                dy = rng.randint(by + 1, by + bh - 2)
            else:
                dx = bx
                dy = rng.randint(by + 1, by + bh - 2)
            gm.set_tile(dx, dy, DOOR)

            for _ in range(rng.randint(1, 3)):
                cx = rng.randint(bx + 1, bx + bw - 2)
                cy = rng.randint(by + 1, by + bh - 2)
                if rng.random() < 0.5:
                    starting_items.append(Item.ammo_crate(cx, cy, amount=rng.choice([6, 8, 10])))
                else:
                    starting_items.append(Item.med_crate(cx, cy, amount=rng.choice([3, 4, 5])))

        rock_count = (w * h) // 140
        for _ in range(rock_count):
            x = rng.randrange(0, w)
            y = rng.randrange(0, h)
            if gm.tile_at(x, y) == SAND and rng.random() < 0.8:
                gm.set_tile(x, y, ROCK)

        return gm, starting_items

    def los(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        for x, y in tcod.los.bresenham((x0, y0), (x1, y1)).tolist():
            if (x, y) == (x0, y0):
                continue
            if not self.in_bounds(x, y):
                return False
            if self.blocks_los(x, y):
                return (x, y) == (x1, y1)  # allow hitting a blocking tile only if it's the target
        return True

    def cover_bonus_at(self, target_x: int, target_y: int) -> int:
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = target_x + dx, target_y + dy
            if self.in_bounds(nx, ny) and self.tile_at(nx, ny) == ROCK:
                return 20  # 20% harder to hit
        return 0
