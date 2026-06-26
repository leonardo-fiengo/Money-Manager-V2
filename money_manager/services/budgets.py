from money_manager.db.connection import get_db
from money_manager.utils.dates import today_iso


def current_month():
    return today_iso()[:7]


def list_budgets(month=None):
    month = month or current_month()
    return get_db().execute(
        """
        SELECT b.*, c.name AS category_name, c.color AS category_color, c.icon AS category_icon,
               COALESCE((
                   SELECT SUM(t.amount)
                   FROM transactions t
                   WHERE t.status = 'posted'
                     AND t.type = 'expense'
                     AND t.category = c.name
                     AND substr(t.date, 1, 7) = b.month
               ), 0) AS spent_amount
        FROM budgets b
        JOIN categories c ON c.id = b.category_id
        WHERE b.month = ?
        ORDER BY c.name
        """,
        (month,),
    ).fetchall()


def get_budget(budget_id):
    return get_db().execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()


def upsert_budget(data):
    _validate_budget(data)
    db = get_db()
    db.execute(
        """
        INSERT INTO budgets (month, category_id, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(month, category_id)
        DO UPDATE SET amount = excluded.amount, updated_at = CURRENT_TIMESTAMP
        """,
        (data["month"], int(data["category_id"]), float(data["amount"])),
    )
    db.commit()


def delete_budget(budget_id):
    db = get_db()
    db.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    db.commit()


def budget_summary(month=None):
    budgets = list_budgets(month)
    total_budget = sum(row["amount"] for row in budgets)
    total_spent = sum(row["spent_amount"] for row in budgets)
    return {
        "month": month or current_month(),
        "total_budget": round(total_budget, 2),
        "total_spent": round(total_spent, 2),
        "remaining": round(total_budget - total_spent, 2),
    }


def _validate_budget(data):
    if not data.get("month") or len(data["month"]) != 7:
        raise ValueError("Budget month must use YYYY-MM.")
    if int(data.get("category_id") or 0) <= 0:
        raise ValueError("Budget category is required.")
    if float(data.get("amount") or 0) < 0:
        raise ValueError("Budget amount cannot be negative.")
