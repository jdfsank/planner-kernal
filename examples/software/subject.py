def slug(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError("nonempty text required")
    return "-".join(value.lower().split())
