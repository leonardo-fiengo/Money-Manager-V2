def clean_amount(value):
    from money_manager.utils.money import money_value
    return money_value(value or 0)


def empty_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None
