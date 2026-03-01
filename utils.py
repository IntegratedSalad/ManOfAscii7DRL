import math

def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))