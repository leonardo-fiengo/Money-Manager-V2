from datetime import date, datetime, timedelta
import calendar


DATE_FORMAT = "%Y-%m-%d"


def today_iso():
    return date.today().isoformat()


def parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, DATE_FORMAT).date()


def add_frequency(value, frequency):
    current = parse_date(value)
    if frequency == "daily":
        return current + timedelta(days=1)
    if frequency == "weekly":
        return current + timedelta(weeks=1)
    if frequency == "yearly":
        year = current.year + 1
        return current.replace(year=year, day=min(current.day, calendar.monthrange(year, current.month)[1]))
    if frequency == "monthly":
        month = current.month + 1
        year = current.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(current.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise ValueError(f"Unsupported frequency: {frequency}")


def next_settlement_date(transaction_date, settlement_day):
    base = parse_date(transaction_date)
    day = settlement_day or 15
    year = base.year
    month = base.month
    if base.day >= day:
        month += 1
        if month == 13:
            month = 1
            year += 1
    return date(year, month, day)
