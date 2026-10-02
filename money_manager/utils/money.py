"""Exact monetary input and integer storage; floats are only presentation values."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_COLUMNS = {
    "accounts": ("opening_balance",),
    "transactions": ("amount", "amount_eur"),
    "recurring_rules": ("amount",),
    "loans": ("principal_amount", "expected_total_amount"),
    "loan_payments": ("amount",),
    "budgets": ("amount",),
    "balance_checks": ("expected", "actual", "adjustment"),
    "savings_pots": ("target", "reserved"),
    "transaction_splits": ("amount_eur",),
    "pot_movements": ("delta",),
}


def decimal_money(value, *, rounding=False):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal("999999999"):
            raise ValueError
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not rounding and rounded != amount:
            raise ValueError
        return rounded
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid amount with at most two decimal places.") from None


def to_minor(value, *, rounding=False):
    return int(decimal_money(value, rounding=rounding) * 100)


def money_value(value):
    return float(decimal_money(value))


def money_sum(values):
    return sum(to_minor(value, rounding=True) for value in values) / 100


def storage_row(table, row):
    """Accept exported/current rows and omit generated display columns."""
    result = dict(row)
    for column in MONEY_COLUMNS.get(table, ()):
        if column in result:
            result.setdefault(column + "_minor", to_minor(result.pop(column), rounding=True))
    return result


def insert_row(db, table, row):
    row = storage_row(table, row)
    columns = list(row)
    return db.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        [row[column] for column in columns],
    )
