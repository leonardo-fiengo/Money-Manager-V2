import json
import math
from datetime import date

from money_manager.db.connection import get_db
from money_manager.services.accounts import get_account
from money_manager.utils.dates import next_settlement_date, today_iso
from money_manager.utils.exchange import to_eur

TRANSACTION_TYPES = {"expense", "income", "investment", "transfer"}
STATUSES = {"posted", "pending"}


def _value(data, key, default=None):
    if hasattr(data, "keys") and key in data.keys():
        return data[key]
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def list_transactions(filters=None, include_pending=False):
    filters = filters or {}
    where = []
    params = []
    if not include_pending:
        where.append("t.status = 'posted'")
    if filters.get("type"):
        where.append("t.type = ?")
        params.append(filters["type"])
    if filters.get("account_id"):
        where.append("t.account_id = ?")
        params.append(filters["account_id"])
    if filters.get("category"):
        where.append("t.category = ?")
        params.append(filters["category"])
    if filters.get("search"):
        where.append("(t.description LIKE ? OR m.name LIKE ? OR t.category LIKE ?)")
        term = f"%{filters['search']}%"
        params.extend([term, term, term])
    for key, operator in (("start", ">="), ("end", "<=")):
        if filters.get(key):
            where.append(f"t.date {operator} ?")
            params.append(filters[key])

    sql = """
        SELECT t.*, a.name AS account_name, a.logo AS account_logo,
               d.name AS destination_account_name, d.logo AS destination_account_logo,
               m.name AS merchant_name,
               c.icon AS category_icon, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN accounts d ON d.id = t.destination_account_id
        LEFT JOIN merchants m ON m.id = t.merchant_id
        LEFT JOIN categories c ON c.name = t.category
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.date DESC, t.id DESC"
    return get_db().execute(sql, params).fetchall()


def get_transaction(transaction_id):
    return get_db().execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()


def create_transaction(data, create_settlement=True):
    _validate_transaction_data(data)
    currency = (_value(data, "currency", "EUR") or "EUR").upper()
    amount = float(_value(data, "amount"))
    amount_eur = to_eur(amount, currency)
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO transactions (
            date, type, amount, currency, amount_eur, category, description, account_id,
            destination_account_id, merchant_id, status, is_credit_card_settlement,
            settlement_for_transaction_id, recurring_rule_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _value(data, "date") or today_iso(),
            _value(data, "type"),
            amount,
            currency,
            amount_eur,
            _value(data, "category"),
            _value(data, "description"),
            _value(data, "account_id"),
            _value(data, "destination_account_id"),
            _value(data, "merchant_id"),
            _value(data, "status", "posted"),
            int(_value(data, "is_credit_card_settlement", False)),
            _value(data, "settlement_for_transaction_id"),
            _value(data, "recurring_rule_id"),
        ),
    )
    transaction_id = cursor.lastrowid

    if create_settlement and _value(data, "type") == "expense" and _value(data, "status", "posted") == "posted":
        _create_credit_card_settlement(db, transaction_id, data)

    db.commit()
    return transaction_id


def update_transaction(transaction_id, data):
    _validate_transaction_data(data)
    currency = (_value(data, "currency", "EUR") or "EUR").upper()
    amount = float(_value(data, "amount"))
    amount_eur = to_eur(amount, currency)
    db = get_db()
    db.execute(
        """
        UPDATE transactions
        SET date = ?, type = ?, amount = ?, currency = ?, amount_eur = ?, category = ?, description = ?,
            account_id = ?, destination_account_id = ?, merchant_id = ?,
            status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            _value(data, "date") or today_iso(),
            _value(data, "type"),
            amount,
            currency,
            amount_eur,
            _value(data, "category"),
            _value(data, "description"),
            _value(data, "account_id"),
            _value(data, "destination_account_id"),
            _value(data, "merchant_id"),
            _value(data, "status", "posted"),
            transaction_id,
        ),
    )
    db.commit()


def create_settlement_for_transaction(transaction_id):
    db = get_db()
    tx = get_transaction(transaction_id)
    if not tx or tx["type"] != "expense" or tx["status"] != "posted":
        return
    existing = db.execute(
        "SELECT id FROM transactions WHERE settlement_for_transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    if existing:
        return
    _create_credit_card_settlement(db, transaction_id, tx)
    db.commit()


def delete_transaction(transaction_id):
    db = get_db()
    with db:
        rows = db.execute("SELECT * FROM transactions WHERE id = ? OR settlement_for_transaction_id = ? ORDER BY id", (transaction_id, transaction_id)).fetchall()
        if not rows:
            return None
        cursor = db.execute("INSERT INTO transaction_trash (payload) VALUES (?)", (json.dumps([dict(row) for row in rows]),))
        db.execute("DELETE FROM transactions WHERE settlement_for_transaction_id = ?", (transaction_id,))
        db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    return cursor.lastrowid


def restore_transaction(trash_id):
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        trash = db.execute("SELECT * FROM transaction_trash WHERE id = ? AND restored_at IS NULL", (trash_id,)).fetchone()
        if not trash:
            raise ValueError("This transaction has already been restored or is unavailable.")
        rows = json.loads(trash["payload"])
        for row in sorted(rows, key=lambda r: bool(r["settlement_for_transaction_id"])):
            if db.execute("SELECT 1 FROM transactions WHERE id = ?", (row["id"],)).fetchone():
                raise ValueError("A transaction with this ID already exists. Nothing was restored.")
            # Removed recurring rules or merchants must not prevent recovery.
            for column, table in (("merchant_id", "merchants"), ("recurring_rule_id", "recurring_rules"), ("settlement_for_transaction_id", "transactions")):
                if row[column] and not db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row[column],)).fetchone():
                    row[column] = None
            columns = list(row)
            db.execute(f"INSERT INTO transactions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])
        db.execute("UPDATE transaction_trash SET restored_at = CURRENT_TIMESTAMP WHERE id = ?", (trash_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise


def _validate_transaction_data(data):
    tx_type = _value(data, "type")
    status = _value(data, "status", "posted")
    amount = float(_value(data, "amount") or 0)
    account_id = _value(data, "account_id")
    account = get_account(account_id)
    destination_id = _value(data, "destination_account_id")
    currency = (_value(data, "currency", "EUR") or "EUR").upper()

    if tx_type not in TRANSACTION_TYPES:
        raise ValueError("Unsupported transaction type.")
    if status not in STATUSES:
        raise ValueError("Unsupported transaction status.")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if len(currency) != 3:
        raise ValueError("Currency must be a 3-letter code.")
    if not account:
        raise ValueError("Transaction account is required.")
    try:
        date.fromisoformat(_value(data, "date") or today_iso())
    except ValueError:
        raise ValueError("Enter a valid transaction date.") from None
    if tx_type == "transfer":
        if not destination_id:
            raise ValueError("Transfers require a destination account.")
        if int(destination_id) == int(account_id):
            raise ValueError("Transfer accounts must be different.")
        if not get_account(destination_id):
            raise ValueError("Destination account does not exist.")
    elif destination_id:
        raise ValueError("Only transfers can use a destination account.")


def _create_credit_card_settlement(db, transaction_id, data):
    account = get_account(_value(data, "account_id"))
    if not account or account["type"] != "credit_card" or not account["settlement_account_id"]:
        return

    currency = (_value(data, "currency", "EUR") or "EUR").upper()
    amount = float(_value(data, "amount"))
    db.execute(
        """
        INSERT INTO transactions (
            date, type, amount, currency, amount_eur, category, description, account_id,
            destination_account_id, merchant_id, status, is_credit_card_settlement,
            settlement_for_transaction_id
        )
        VALUES (?, 'transfer', ?, ?, ?, 'Credit card settlement', ?, ?, ?, NULL, 'pending', 1, ?)
        """,
        (
            next_settlement_date(_value(data, "date") or today_iso(), account["settlement_day"]).isoformat(),
            amount,
            currency,
            to_eur(amount, currency),
            f"Settlement for {_value(data, 'description') or 'credit card expense'}",
            account["settlement_account_id"],
            _value(data, "account_id"),
            transaction_id,
        ),
    )
