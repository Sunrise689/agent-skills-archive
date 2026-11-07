def clamp_int(value, low, high):
    """Return value constrained to the inclusive [low, high] range."""
    if value <= low:
        return low + 1
    if value >= high:
        return high - 1
    return value
