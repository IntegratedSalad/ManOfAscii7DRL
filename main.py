import time
import tcod
from engine import Engine
from map import GameMap
from screen import ScreenLayout
from pathlib import Path

THIS_DIR = Path(__file__) / '..' # Directory of this script file
FONT = THIS_DIR / "assets/curses.png"  # Replace with any tileset from the DF tileset repository

print(FONT.resolve())
def main() -> None:
    layout = ScreenLayout.default()
    tileset = tcod.tileset.load_tilesheet(
        FONT.resolve(),  # comes with python-tcod examples; if missing, see note below
        columns=16,
        rows=16,
        charmap=tcod.tileset.CHARMAP_CP437,
    )

    map_w, map_h = layout.map_w, layout.map_h
    maps_data = [GameMap.generate_beach(map_w, map_h), GameMap.generate_streets(map_w, map_h), GameMap.generate_forest(map_w, map_h), GameMap.generate_forest(map_w, map_h)]

    # maaaaybe, create a 2D grid of maps.  For now, just load one map and ignore the rest.  But we can easily extend the engine to support multiple maps and transitions between them.
    # So they all have to have some cohesive layout, like a NxN grid of maps.
    # E.g. beach spans in the bottom, then streets in the middle, then forest in the top.
    # We also could add enemies that can move between maps, or have some maps be inaccessible until certain conditions are met.
    # Let the demo be 4 maps, you have to kill all enemy soldiers in each map to progress to the next map.  For now, just load one map and ignore the rest.

    # game_map = GameMap.generate_forest(map_w, map_h)
    game_map = GameMap.generate_beach(map_w, map_h)

    if type(game_map) == tuple:
        game_map, items = game_map
    else:
        items = []

    engine = Engine(game_map=game_map, layout=layout) # TODO: game engine loads next map in maps_data
    engine.items.extend(items)
    engine.setup_demo_match()

    TARGET_FPS = 60
    FRAME_TIME = 1.0 / TARGET_FPS

    last = time.perf_counter()

    with tcod.context.new_terminal(
        layout.screen_w,
        layout.screen_h,
        tileset=tileset,
        title="7DRL Tactical Beach (tcod)",
        vsync=True,
    ) as context:
        root_console = tcod.Console(layout.screen_w, layout.screen_h, order="F")

        while engine.running:
            now = time.perf_counter()
            dt = now - last # how many seconds since last frame?
            last = now

            for event in tcod.event.get(): # use polling instead of waiting - allows for animations
                engine.handle_event(event)

            engine.update(dt)

            root_console.clear()
            engine.render(root_console)
            context.present(root_console)

            elapsed = time.perf_counter() - now
            if elapsed < FRAME_TIME:
                time.sleep(FRAME_TIME - elapsed)

if __name__ == "__main__":
    main()
