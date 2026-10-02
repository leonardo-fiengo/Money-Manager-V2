from money_manager.db.connection import get_db
from money_manager.utils.money import to_minor, money_value
from money_manager.db.atomic import atomic
from money_manager.services.transactions import create_transaction
from money_manager.utils.dates import add_frequency, parse_date, today_iso
from money_manager.utils.exchange import to_eur


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
            name, type, amount_minor, category, description, account_id, merchant_id,
            visual_mode, is_subscription, frequency, next_due_date, currency, amount_eur_minor, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            data["name"],
            data["type"],
            to_minor(data["amount"]),
            data.get("category"),
            data.get("description"),
            data["account_id"],
            data.get("merchant_id"),
            data.get("visual_mode") or "auto",
            int(bool(data.get("is_subscription"))),
            data["frequency"],
            data.get("next_due_date") or today_iso(),
            data.get('currency') or 'EUR',
            to_minor(to_eur(data['amount'],data.get('currency') or 'EUR')),
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
        SET name = ?, type = ?, amount_minor = ?, category = ?, description = ?,
            account_id = ?, merchant_id = ?, visual_mode = ?, is_subscription = ?, frequency = ?,
            next_due_date = ?, currency = ?, amount_eur_minor = ?, is_active = ?
        WHERE id = ?
        """,
        (
            data["name"],
            data["type"],
            to_minor(data["amount"]),
            data.get("category"),
            data.get("description"),
            data["account_id"],
            data.get("merchant_id"),
            data.get("visual_mode") or "auto",
            int(bool(data.get("is_subscription"))),
            data["frequency"],
            data.get("next_due_date") or today_iso(),
            data.get('currency') or 'EUR',
            to_minor(to_eur(data['amount'],data.get('currency') or 'EUR')),
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
    with atomic(db):
        rules = db.execute("SELECT * FROM recurring_rules WHERE is_active = 1 AND next_due_date <= ?", (until_date.isoformat(),)).fetchall()
        for rule in rules:
            next_due = parse_date(rule["next_due_date"])
            while next_due <= until_date:
                claimed = db.execute("INSERT OR IGNORE INTO recurring_occurrences (recurring_rule_id, due_date) VALUES (?, ?)",
                                     (rule["id"], next_due.isoformat())).rowcount
                if claimed and not db.execute("SELECT 1 FROM transactions WHERE recurring_rule_id = ? AND date = ?", (rule["id"], next_due.isoformat())).fetchone():
                    create_transaction(dict(date=next_due.isoformat(), type=rule["type"], amount=rule["amount"],
                        category=rule["category"], description=rule["description"] or rule["name"],
                        account_id=rule["account_id"], merchant_id=rule["merchant_id"], currency=rule['currency'], is_subscription=rule['is_subscription'], status="pending", recurring_rule_id=rule["id"]),
                        create_settlement=False, commit=False)
                next_due = add_frequency(next_due, rule["frequency"])
            db.execute("UPDATE recurring_rules SET next_due_date = ? WHERE id = ?", (next_due.isoformat(), rule["id"]))


def _validate_rule_data(data):
    if not (data.get("name") or "").strip():
        raise ValueError("Recurring rule name is required.")
    if data.get("type") not in {"expense", "income", "investment"}:
        raise ValueError("Unsupported recurring type.")
    if money_value(data.get("amount") or 0) <= 0:
        raise ValueError("Recurring amount must be greater than zero.")
    if data.get("frequency") not in {"daily", "weekly", "monthly", "yearly"}:
        raise ValueError("Unsupported recurring frequency.")
    parse_date(data.get("next_due_date") or today_iso())
    from money_manager.services.accounts import get_account
    if not get_account(data.get("account_id")):
        raise ValueError("Choose an existing account.")
    if data.get("visual_mode") not in {None, "", "auto", "merchant_logo", "standard"}:
        raise ValueError("Unsupported recurring visual mode.")
    if (data.get('currency') or 'EUR') not in {'EUR','USD','GBP','CHF'}:
        raise ValueError('Choose EUR, USD, GBP, or CHF.')

