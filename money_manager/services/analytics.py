from collections import defaultdict
from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances


def dashboard_period(period="month"):
    today = date.today()
    if period == "all":
        return dict(period=period, start=None, end=None, label="All time")
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        label = end.strftime("%B %Y")
    elif period == "year":
        start, end, label = today.replace(month=1, day=1), today, "This year"
    else:
        period = "month"
        start, end, label = today.replace(day=1), today, today.strftime("%B %Y")
    return dict(period=period, start=start.isoformat(), end=end.isoformat(), label=label)


def _posted_transactions(start=None, end=None):
    sql, params = "SELECT * FROM transactions WHERE status = 'posted'", []
    if start:
        sql += " AND date >= ?"
        params.append(start)
    if end:
        sql += " AND date <= ?"
        params.append(end)
    return get_db().execute(sql, params).fetchall()


def _row_value(row, key, default=None):
    return row[key] if key in row.keys() else default


def _amount_eur(row):
    stored_amount = _row_value(row, "amount_eur")
    return float(stored_amount if stored_amount not in (None, 0) else row["amount"])


def dashboard_metrics(start=None, end=None):
    totals = {"income": 0, "expense": 0, "investment": 0}
    for tx in _posted_transactions(start, end):
        if tx["type"] in totals:
            totals[tx["type"]] += _amount_eur(tx)

    net_balance = sum(account["balance"] for account in account_balances())
    savings_rate = 0
    if totals["income"]:
        savings_rate = ((totals["income"] - totals["expense"] - totals["investment"]) / totals["income"]) * 100
    return {
        "income": round(totals["income"], 2),
        "expenses": round(totals["expense"], 2),
        "investments": round(totals["investment"], 2),
        "net_balance": round(net_balance, 2),
        "savings_rate": round(savings_rate, 1),
    }


def monthly_summary(start=None, end=None):
    rows = defaultdict(lambda: {"income": 0, "expenses": 0, "investments": 0})
    for tx in _posted_transactions(start, end):
        month = tx["date"][:7]
        amount = _amount_eur(tx)
        if tx["type"] == "income":
            rows[month]["income"] += amount
        elif tx["type"] == "expense":
            rows[month]["expenses"] += amount
        elif tx["type"] == "investment":
            rows[month]["investments"] += amount
    return [
        {
            "month": month,
            "income": round(values["income"], 2),
            "expenses": round(values["expenses"], 2),
            "investments": round(values["investments"], 2),
        }
        for month, values in sorted(rows.items())
    ]


def expenses_by_category(start=None, end=None):
    rows = defaultdict(float)
    for tx in _posted_transactions(start, end):
        if tx["type"] == "expense":
            rows[tx["category"] or "Uncategorized"] += _amount_eur(tx)

    categories = {
        row["name"]: row
        for row in get_db().execute("SELECT name, icon, color FROM categories").fetchall()
    }
    output = []
    for category, total in sorted(rows.items(), key=lambda item: item[1], reverse=True):
        category_row = categories.get(category)
        output.append(
            {
                "category": category,
                "total": round(total, 2),
                "icon": (category_row["icon"] or category[:1]) if category_row else "$",
                "color": category_row["color"] if category_row else "#147d64",
            }
        )
    return output


def cumulative_balance():
    rows = defaultdict(float)
    for tx in _posted_transactions():
        amount = _amount_eur(tx)
        if tx["type"] == "income":
            rows[tx["date"]] += amount
        elif tx["type"] in ("expense", "investment"):
            rows[tx["date"]] -= amount
    for check in get_db().execute("SELECT created_at, adjustment FROM balance_checks WHERE adjustment != 0"):
        rows[check["created_at"][:10]] += check["adjustment"]
    balance = sum(a["opening_balance"] for a in account_balances())
    output = []
    for day, change in sorted(rows.items()):
        balance += change
        output.append({"date": day, "balance": round(balance, 2)})
    return output


def weekday_spending():
    labels = {
        "0": "Sunday",
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday",
    }
    rows = get_db().execute(
        """
        SELECT date, amount, currency, amount_eur
        FROM transactions
        WHERE status = 'posted' AND type = 'expense'
        """
    ).fetchall()
    totals = defaultdict(float)
    for row in rows:
        weekday = get_db().execute("SELECT strftime('%w', ?) AS weekday", (row["date"],)).fetchone()["weekday"]
        totals[weekday] += _amount_eur(row)
    return [{"weekday": labels[key], "total": round(totals[key], 2)} for key in sorted(totals)]


def largest_expenses(limit=10):
    rows = get_db().execute(
        """
        SELECT t.*, a.name AS account_name, a.logo AS account_logo,
               m.name AS merchant_name, m.logo AS merchant_logo,
               c.icon AS category_icon, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN merchants m ON m.id = t.merchant_id
        LEFT JOIN categories c ON c.name = t.category
        WHERE t.status = 'posted' AND t.type = 'expense'
        """
    ).fetchall()
    sorted_rows = sorted(rows, key=_amount_eur, reverse=True)[:limit]
    return [dict(row, amount=round(_amount_eur(row), 2), currency="EUR") for row in sorted_rows]


