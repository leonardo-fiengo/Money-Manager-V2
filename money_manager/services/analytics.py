from collections import defaultdict
from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.utils.money import money_sum, to_minor
from money_manager.services.accounts import account_balances
from money_manager.services.transaction_details import expense_allocations


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
    sql, params = "SELECT * FROM ledger_transactions WHERE status = 'posted'", []
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
    linked_income = {row["related_transaction_id"] for row in get_db().execute("SELECT related_transaction_id FROM transaction_links")}
    for tx in _posted_transactions(start, end):
        if tx["type"] == "expense" or (tx["type"] == "income" and tx["id"] in linked_income):
            continue
        if tx["type"] in totals:
            totals[tx["type"]] += tx["amount_eur_minor"]
    totals["expense"] = sum(to_minor(row["amount"]) for row in expense_allocations(start, end))
    totals = {key: value / 100 for key, value in totals.items()}

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
    linked_income = {row["related_transaction_id"] for row in get_db().execute("SELECT related_transaction_id FROM transaction_links")}
    for tx in _posted_transactions(start, end):
        month = tx["date"][:7]
        amount = _amount_eur(tx)
        if tx["type"] == "income" and tx["id"] not in linked_income:
            rows[month]["income"] += amount
        elif tx["type"] == "investment":
            rows[month]["investments"] += amount
    for allocation in expense_allocations(start, end):
        rows[allocation["date"][:7]]["expenses"] += allocation["amount"]
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
    for allocation in expense_allocations(start, end):
        rows[allocation["category"]] += allocation["amount"]

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


def spending_by_tag():
    amounts = defaultdict(float)
    for row in expense_allocations():
        amounts[row["transaction_id"]] += row["amount"]
    totals = defaultdict(float)
    for tag in get_db().execute("SELECT transaction_id, tag FROM transaction_tags"):
        if tag["transaction_id"] in amounts:
            totals[tag["tag"]] += amounts[tag["transaction_id"]]
    return [dict(tag=tag, total=round(total, 2)) for tag, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)]


def cumulative_balance():
    # Ledger amounts are already converted to EUR and transfer mirrors are
    # excluded by the view. A transfer moves money, never combined net worth.
    rows = defaultdict(int)
    for tx in _posted_transactions():
        amount = tx['amount_eur_minor']
        if tx["type"] == "income":
            rows[tx["date"]] += amount
        elif tx["type"] in ("expense", "investment"):
            rows[tx["date"]] -= amount
    for check in get_db().execute("""SELECT COALESCE(s.through_date,substr(b.created_at,1,10)) AS date,
            b.adjustment_minor FROM balance_checks b
            LEFT JOIN reconciliation_sessions s ON s.id=b.session_id WHERE b.adjustment_minor != 0"""):
        rows[check['date']] += check['adjustment_minor']
    balance = get_db().execute('SELECT COALESCE(SUM(opening_balance_minor),0) AS total FROM accounts').fetchone()['total']
    output = []
    for day, change in sorted(rows.items()):
        balance += change
        output.append({"date": day, "balance": balance / 100})
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
    totals = defaultdict(float)
    for row in expense_allocations():
        weekday = str((date.fromisoformat(row["date"]).weekday() + 1) % 7)
        totals[weekday] += row["amount"]
    return [{"weekday": labels[key], "total": round(totals[key], 2)} for key in sorted(totals)]


def largest_expenses(limit=10):
    rows = get_db().execute(
        """
        SELECT t.*, a.name AS account_name, a.logo AS account_logo,
               m.name AS merchant_name, m.logo AS merchant_logo,
               c.icon AS category_icon, c.color AS category_color
        FROM ledger_transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN merchants m ON m.id = t.merchant_id
        LEFT JOIN categories c ON c.name = t.category
        WHERE t.status = 'posted' AND t.type = 'expense'
        """
    ).fetchall()
    net_amounts = defaultdict(float)
    for allocation in expense_allocations():
        net_amounts[allocation["transaction_id"]] += allocation["amount"]
    sorted_rows = sorted(rows, key=lambda row: net_amounts[row["id"]], reverse=True)[:limit]
    return [dict(row, amount=round(net_amounts[row["id"]], 2), currency="EUR") for row in sorted_rows]




def six_month_flow():
    today = date.today()
    month_number = today.year * 12 + today.month - 1
    keys = [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(month_number - 5, month_number + 1)]
    values = {row["month"]: row for row in monthly_summary(keys[0] + "-01", today.isoformat())}
    return [values.get(key, dict(month=key, income=0, expenses=0, investments=0)) for key in keys]
