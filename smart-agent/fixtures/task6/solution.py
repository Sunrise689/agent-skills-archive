def running_totals(values):
    """Return the cumulative sum after every input value."""
    total = 0
    result = []
    for value in values:
        total += value
        result.append(total)
    return result[1:]
