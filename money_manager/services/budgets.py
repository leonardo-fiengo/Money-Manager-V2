from calendar import monthrange
from datetime import date, timedelta
import json
from functools import lru_cache

from money_manager.db.connection import get_db
from money_manager.utils.money import to_minor, money_value, money_sum
from money_manager.services.transaction_details import expense_allocations
from money_manager.utils.dates import today_iso


def current_month():
    return today_iso()[:7]


def list_budgets(month=None):
    month = month or current_month()
    rows = get_db().execute(
        """
        SELECT b.*, c.name AS category_name, c.color AS category_color, c.icon AS category_icon,
               0 AS spent_amount
        FROM budgets b
        JOIN categories c ON c.id = b.category_id
        WHERE b.month = ?
        ORDER BY c.name
        """,
        (month,),
    ).fetchall()
    monthly_spend = {}
    for allocation in expense_allocations():
        key = (allocation["date"][:7], allocation["category"])
        monthly_spend[key] = monthly_spend.get(key, 0) + allocation["amount"]
    budget_history = {(row["month"], row["category_id"]): row for row in get_db().execute("SELECT month, category_id, amount, rollover FROM budgets WHERE month <= ?", (month,))}
    category_names = {row["id"]: row["name"] for row in get_db().execute("SELECT id, name FROM categories")}

    @lru_cache(None)
    def unused_after(budget_month, category_id, depth=0):
        previous_budget = budget_history.get((budget_month, category_id))
        if not previous_budget or depth > 120:
            return 0
        first_day = date.fromisoformat(budget_month + "-01")
        previous_month = (first_day - timedelta(days=1)).strftime("%Y-%m")
        carried = unused_after(previous_month, category_id, depth + 1) if previous_budget["rollover"] else 0
        spent = monthly_spend.get((budget_month, category_names[category_id]), 0)
        return max(0, previous_budget["amount"] + carried - spent)
    first = date.fromisoformat(month + "-01")
    previous = (first - timedelta(days=1)).strftime("%Y-%m")
    days_in_month = monthrange(first.year, first.month)[1]
    elapsed = min(days_in_month, max(0, (date.today() - first).days + 1))
    result = []
    for row in rows:
        row = dict(row, spent_amount=round(monthly_spend.get((month, row["category_name"]), 0), 2))
        carried = unused_after(previous, row["category_id"]) if row["rollover"] else 0
        available = row["amount"] + carried
        projected = row["spent_amount"] / elapsed * days_in_month if elapsed else 0
        remaining = available - row["spent_amount"]
        days_left = days_in_month - elapsed
        result.append(dict(row, rollover_amount=round(carried, 2), available_amount=round(available, 2), projected=round(projected, 2), remaining_per_day=round(remaining / days_left, 2) if days_left else 0, month_elapsed=round(elapsed / days_in_month * 100, 1)))
    return result


def get_budget(budget_id):
    return get_db().execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()


def upsert_budget(data):
    _validate_budget(data)
    db = get_db()
    db.execute(
        """
        INSERT INTO budgets (month, category_id, amount_minor, rollover)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(month, category_id)
        DO UPDATE SET amount_minor = excluded.amount_minor, rollover = excluded.rollover, updated_at = CURRENT_TIMESTAMP
        """,
        (data["month"], int(data["category_id"]), to_minor(data["amount"]), int(bool(data.get("rollover")))),
    )
    db.commit()


def delete_budget(budget_id):
    db = get_db()
    db.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    db.commit()


def budget_summary(month=None):
    budgets = list_budgets(month)
    total_budget = money_sum(row["available_amount"] for row in budgets)
    total_spent = money_sum(row["spent_amount"] for row in budgets)
    return {
        "month": month or current_month(),
        "total_budget": round(total_budget, 2),
        "total_spent": round(total_spent, 2),
        "remaining": round(total_budget - total_spent, 2),
    }


def copy_previous_budgets(month):
    first = date.fromisoformat(month + "-01")
    previous = (first - timedelta(days=1)).strftime("%Y-%m")
    db = get_db()
    db.execute("""
        INSERT OR IGNORE INTO budgets (month, category_id, amount_minor, rollover)
        SELECT ?, category_id, amount_minor, rollover FROM budgets WHERE month = ?
    """, (month, previous))
    db.commit()


def list_budget_templates():
    return get_db().execute("SELECT id, name FROM budget_templates ORDER BY name").fetchall()


def save_budget_template(name, month):
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise ValueError("Enter a template name under 80 characters.")
    rows = get_db().execute("SELECT category_id, amount, rollover FROM budgets WHERE month = ?", (month,)).fetchall()
    if not rows:
        raise ValueError("Set at least one budget before saving a template.")
    db = get_db()
    db.execute("INSERT INTO budget_templates (name, rows_json) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET rows_json = excluded.rows_json", (name, json.dumps([dict(row) for row in rows])))
    db.commit()


def apply_budget_template(template_id, month):
    date.fromisoformat(month + "-01")
    db = get_db()
    template = db.execute("SELECT * FROM budget_templates WHERE id = ?", (template_id,)).fetchone()
    if not template:
        raise ValueError("Choose an existing template.")
    with db:
        for row in json.loads(template["rows_json"]):
            if db.execute("SELECT 1 FROM categories WHERE id = ?", (row["category_id"],)).fetchone():
                db.execute("INSERT OR IGNORE INTO budgets (month, category_id, amount_minor, rollover) VALUES (?, ?, ?, ?)", (month, row["category_id"], to_minor(row["amount"]), row["rollover"]))


def _validate_budget(data):
    try:
        date.fromisoformat((data.get("month") or "") + "-01")
    except ValueError:
        raise ValueError("Budget month must use YYYY-MM.")
    if int(data.get("category_id") or 0) <= 0:
        raise ValueError("Budget category is required.")
    if money_value(data.get("amount") or 0) < 0:
        raise ValueError("Budget amount cannot be negative.")
    category = get_db().execute("SELECT type FROM categories WHERE id = ?", (data["category_id"],)).fetchone()
    if not category or category["type"] not in {"expense", "any"}:
        raise ValueError("Choose an expense category.")


def budget_suggestions():
    today = date.today().replace(day=1)
    number = today.year * 12 + today.month - 1 - 3
    start = f"{number // 12:04d}-{number % 12 + 1:02d}-01"
    totals = {}
    for row in expense_allocations(start, (today - timedelta(days=1)).isoformat()):
        totals[row["category"]] = totals.get(row["category"], 0) + to_minor(row["amount"])
    categories = get_db().execute("SELECT id, name FROM categories WHERE is_active = 1 AND type IN ('expense', 'any')").fetchall()
    suggestions = [dict(category, amount=round(totals[category["name"]] / 300, 2)) for category in categories if totals.get(category["name"], 0) > 0]
    return sorted(suggestions, key=lambda row: row["amount"], reverse=True)[:3]
