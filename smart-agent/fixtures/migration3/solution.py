def parse_kv(text):
    """Parse semicolon-separated key=value pairs; trim spaces and let last win."""
    result = {}
    for item in text.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result
