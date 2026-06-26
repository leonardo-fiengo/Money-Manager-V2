def clean_amount(value):
    return round(float(value or 0), 2)


def empty_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None
