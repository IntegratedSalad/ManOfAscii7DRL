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


    # If you don't have that tilesheet file, easiest quick fix:
    # 1) copy a tilesheet into your project folder, or
    # 2) use tcod.tileset.load_tilesheet with a file you do have.
    # You can also use built-in tileset via tcod.tileset.load_tilesheet from installed package assets
    # (paths differ by install). For 7DRL, just bundle your tilesheet.

    map_w, map_h = layout.map_w, layout.map_h
    game_map = GameMap.generate_default(map_w, map_h)

    engine = Engine(game_map=game_map, layout=layout)
    engine.setup_demo_match()

    with tcod.context.new_terminal(
        layout.screen_w,
        layout.screen_h,
        tileset=tileset,
        title="7DRL Tactical Beach (tcod)",
        vsync=True,
    ) as context:
        root_console = tcod.Console(layout.screen_w, layout.screen_h, order="F")

        while engine.running:
            root_console.clear()
            engine.render(root_console)
            context.present(root_console)

            for event in tcod.event.wait():
                engine.handle_event(event)
                # If one event ends turn etc, we still continue processing input next frame.


if __name__ == "__main__":
    main()
