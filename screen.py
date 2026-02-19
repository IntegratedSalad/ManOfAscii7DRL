from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class ScreenLayout:
    screen_w: int
    screen_h: int

    map_rect: Rect
    soldiers_rect: Rect
    equip_rect: Rect
    log_rect: Rect

    @property
    def map_w(self) -> int:
        return self.map_rect.w

    @property
    def map_h(self) -> int:
        return self.map_rect.h

    @staticmethod
    def default() -> "ScreenLayout":
        # A layout that feels good in 80x50.
        # Left: map. Right: 3 stacked panels.
        screen_w, screen_h = 80, 50
        right_w = 26
        map_w = screen_w - right_w
        map_h = 34

        soldiers_h = 18
        equip_h = 10
        log_h = screen_h - soldiers_h - equip_h

        map_rect = Rect(0, 0, map_w, screen_h)
        soldiers_rect = Rect(map_w, 0, right_w, soldiers_h)
        equip_rect = Rect(map_w, soldiers_h, right_w, equip_h)
        log_rect = Rect(map_w, soldiers_h + equip_h, right_w, log_h)

        return ScreenLayout(
            screen_w=screen_w,
            screen_h=screen_h,
            map_rect=map_rect,
            soldiers_rect=soldiers_rect,
            equip_rect=equip_rect,
            log_rect=log_rect,
        )
