import time
import tcod
from engine import Engine
from map import GameMap
from screen import ScreenLayout
from pathlib import Path

THIS_DIR = Path(__file__) / '..'
FONT = THIS_DIR / "assets/Unknown_curses_12x12.png"

print(FONT.resolve())

def _make_cell(gen_fn, w: int, h: int):
    cell = gen_fn(w, h)
    if isinstance(cell, tuple):
        game_map, crates = cell
    else:
        game_map, crates = cell, []
    game_map.set_blood()
    return game_map, crates

def main() -> None:
    layout = ScreenLayout.default()
    tileset = tcod.tileset.load_tilesheet(
        FONT.resolve(),
        columns=16,
        rows=16,
        charmap=tcod.tileset.CHARMAP_CP437,
    )

    map_w, map_h = layout.map_w, layout.map_h

    gen_by_row = [
        GameMap.generate_streets,  # y=0 top
        GameMap.generate_forest,   # y=1 middle
        GameMap.generate_beach,    # y=2 bottom
    ]
    maps_grid = []
    crates_grid = []
    for gy in range(3):
        row_maps = []
        row_crates = []
        for gx in range(3):
            gm, crates = _make_cell(gen_by_row[gy], map_w, map_h)
            row_maps.append(gm)
            row_crates.append(crates)
        maps_grid.append(row_maps)
        crates_grid.append(row_crates)

    engine = Engine(
        maps_grid=maps_grid,
        crates_grid=crates_grid,
        layout=layout,
        start_gx=1,
        start_gy=2,
    )
    engine.setup_demo_match()
    engine.log.add("Aiming: move cursor with arrows, Enter to shoot, Esc to cancel.")

    TARGET_FPS = 60
    FRAME_TIME = 1.0 / TARGET_FPS
    last = time.perf_counter()

    with tcod.context.new_terminal(
        layout.screen_w,
        layout.screen_h,
        tileset=tileset,
        title="Men Of Ascii (7DRL 2026)",
        vsync=True,
    ) as context:
        root_console = context.new_console(layout.screen_w, layout.screen_h, order="F")

        while engine.running:
            now = time.perf_counter()
            dt = now - last
            last = now

            for event in tcod.event.get():
                engine.handle_event(event)

            engine.update(dt)

            root_console.clear()
            engine.render(root_console)
            context.present(root_console)

            elapsed = time.perf_counter() - now
            if elapsed < FRAME_TIME:
                time.sleep(FRAME_TIME - elapsed)

if __name__ == "__main__":
    import sys
    print(sys.version)
    main()