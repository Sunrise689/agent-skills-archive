def deep_merge(base, patch):
    """Recursively merge patch into a new dictionary without mutating inputs."""
    result = dict(base)
    result.update(patch)
    return result
