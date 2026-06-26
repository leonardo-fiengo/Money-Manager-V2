from money_manager.db.connection import get_db
from money_manager.services.transactions import create_transaction
from money_manager.utils.dates import add_frequency, parse_date, today_iso


def list_rules():
    return get_db().execute(
        """
        SELECT r.*, a.name AS account_name, a.logo AS account_logo, m.name AS merchant_name, m.logo AS merchant_logo
        FROM recurring_rules r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN merchants m ON m.id = r.merchant_id
        ORDER BY r.next_due_date ASC
        """
    ).fetchall()


def get_rule(rule_id):
    return get_db().execute("SELECT * FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()


def create_rule(data):
    _validate_rule_data(data)
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO recurring_rules (
            name, type, amount, category, description, account_id, merchant_id,
            visual_mode, frequency, next_due_date, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            data["name"],
            data["type"],
            float(data["amount"]),
            data.get("category"),
            data.get("description"),
            data["account_id"],
            data.get("merchant_id"),
            data.get("visual_mode") or "auto",
            data["frequency"],
            data.get("next_due_date") or today_iso(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def update_rule(rule_id, data):
    _validate_rule_data(data)
    db = get_db()
    db.execute(
        """
        UPDATE recurring_rules
        SET name = ?, type = ?, amount = ?, category = ?, description = ?,
            account_id = ?, merchant_id = ?, visual_mode = ?, frequency = ?,
            next_due_date = ?, is_active = ?
        WHERE id = ?
        """,
        (
            data["name"],
            data["type"],
            float(data["amount"]),
            data.get("category"),
            data.get("description"),
            data["account_id"],
            data.get("merchant_id"),
            data.get("visual_mode") or "auto",
            data["frequency"],
            data.get("next_due_date") or today_iso(),
            int(data.get("is_active", True)),
            rule_id,
        ),
    )
    db.commit()


def delete_rule(rule_id):
    db = get_db()
    db.execute("DELETE FROM recurring_rules WHERE id = ?", (rule_id,))
    db.commit()


def generate_due_recurring(until_date=None):
    until_date = parse_date(until_date or today_iso())
    db = get_db()
    rules = db.execute("SELECT * FROM recurring_rules WHERE is_active = 1").fetchall()
    for rule in rules:
        next_due = parse_date(rule["next_due_date"])
        while next_due <= until_date:
            exists = db.execute(
                """
                SELECT id FROM transactions
                WHERE recurring_rule_id = ? AND date = ? AND status IN ('pending', 'posted')
                """,
                (rule["id"], next_due.isoformat()),
            ).fetchone()
            if not exists:
                create_transaction(
                    {
                        "date": next_due.isoformat(),
                        "type": rule["type"],
                        "amount": rule["amount"],
                        "category": rule["category"],
                        "description": rule["description"] or rule["name"],
                        "account_id": rule["account_id"],
                        "merchant_id": rule["merchant_id"],
                        "status": "pending",
                        "recurring_rule_id": rule["id"],
                    },
                    create_settlement=False,
                )
            next_due = add_frequency(next_due, rule["frequency"])
        db.execute("UPDATE recurring_rules SET next_due_date = ? WHERE id = ?", (next_due.isoformat(), rule["id"]))
    db.commit()


def _validate_rule_data(data):
    if not (data.get("name") or "").strip():
        raise ValueError("Recurring rule name is required.")
    if data.get("type") not in {"expense", "income", "investment"}:
        raise ValueError("Unsupported recurring type.")
    if float(data.get("amount") or 0) <= 0:
        raise ValueError("Recurring amount must be greater than zero.")
    if data.get("frequency") not in {"daily", "weekly", "monthly", "yearly"}:
        raise ValueError("Unsupported recurring frequency.")
    if data.get("visual_mode") not in {None, "", "auto", "merchant_logo", "standard"}:
        raise ValueError("Unsupported recurring visual mode.")

