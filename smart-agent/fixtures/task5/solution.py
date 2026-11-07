def merge_defaults(config, defaults):
    """Merge config over defaults without mutating either input dictionary."""
    result = defaults
    result.update(config)
    return result
