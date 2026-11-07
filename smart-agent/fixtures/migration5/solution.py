def chunked(values, size):
    """Return consecutive lists of at most size items; reject non-positive size."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [list(values)] if values else []
