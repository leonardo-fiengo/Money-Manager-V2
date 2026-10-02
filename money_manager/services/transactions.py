import json
import math
import re
from contextlib import nullcontext
from datetime import date

from money_manager.db.connection import get_db
from money_manager.services.accounts import get_account
from money_manager.utils.dates import next_settlement_date, today_iso
from money_manager.utils.exchange import to_eur, exchange_quote
from money_manager.utils.money import to_minor, money_value, insert_row
from money_manager.db.atomic import atomic

TRANSACTION_TYPES = {"expense", "income", "investment", "transfer"}
STATUSES = {"posted", "pending"}


def _value(data, key, default=None):
    if hasattr(data, "keys") and key in data.keys():
        return data[key]
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def list_transactions(filters=None, include_pending=False, limit=None, offset=0, count=False):
    filters = filters or {}
    where = []
    params = []
    if not include_pending:
        where.append("t.status = 'posted'")
    if filters.get("type"):
        where.append("t.type = ?")
        params.append(filters["type"])
    if filters.get("account_id"):
        if filters.get('account_activity'):
            where.append("(t.account_id = ? OR (t.type='transfer' AND t.destination_account_id=? AND NOT EXISTS (SELECT 1 FROM transaction_relationships r WHERE r.kind='transfer_pair' AND r.source_transaction_id=t.id)))")
            params.extend([filters['account_id'],filters['account_id']])
        else:
            where.append("t.account_id = ?")
            params.append(filters["account_id"])
    if filters.get("category"):
        where.append("t.category = ?")
        params.append(filters["category"])
    if filters.get("needs_category"):
        where.append("t.category IS NULL AND t.type = 'expense' AND EXISTS (SELECT 1 FROM transaction_import_hashes h WHERE h.transaction_id = t.id)")
    if filters.get("search"):
        tokens = re.findall(r"\w+", filters['search'], flags=re.UNICODE)
        if tokens:
            expression = ' AND '.join('"' + token + '"*' for token in tokens[:12])
            where.append("t.id IN (SELECT rowid FROM transaction_search WHERE transaction_search MATCH ?)")
            params.append(expression)
        else:
            where.append("(t.description LIKE ? OR t.notes LIKE ?)")
            params.extend([f"%{filters['search']}%"]*2)
    if filters.get("tag"):
        where.append("EXISTS (SELECT 1 FROM transaction_tags tags WHERE tags.transaction_id = t.id AND tags.tag = ?)")
        params.append(filters["tag"])
    for key, operator in (("start", ">="), ("end", "<=")):
        if filters.get(key):
            where.append(f"t.date {operator} ?")
            params.append(filters[key])

    sql = """
        SELECT t.*, a.name AS account_name, a.logo AS account_logo,
               d.name AS destination_account_name, d.logo AS destination_account_logo,
               m.name AS merchant_name, m.logo AS merchant_logo,
               c.icon AS category_icon, c.color AS category_color,
               (SELECT group_concat(tag, ', ') FROM transaction_tags tags WHERE tags.transaction_id = t.id) AS tags,
               l.kind AS link_kind, original.description AS linked_expense_description
        FROM ledger_transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN accounts d ON d.id = t.destination_account_id
        LEFT JOIN merchants m ON m.id = t.merchant_id
        LEFT JOIN categories c ON c.name = t.category
        LEFT JOIN transaction_links l ON l.related_transaction_id = t.id
        LEFT JOIN transactions original ON original.id = l.source_transaction_id
    """
    if filters.get('account_activity') and filters.get('account_id'):
        sql = sql.replace('FROM ledger_transactions t','FROM transactions t')
    if where:
        sql += " WHERE " + " AND ".join(where)
    if count:
        return get_db().execute("SELECT COUNT(*) AS total FROM (" + sql + ")", params).fetchone()["total"]
    sql += " ORDER BY t.date DESC, t.id DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([max(1, min(int(limit), 100)), max(0, int(offset))])
    return get_db().execute(sql, params).fetchall()


def get_transaction(transaction_id):
    return get_db().execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()


def create_transaction(data, create_settlement=True, commit=True):
    if commit:
        with atomic(get_db()):
            return _insert_transaction(data, create_settlement)
    return _insert_transaction(data, create_settlement)


def _insert_transaction(data, create_settlement=True):
    _validate_transaction_data(data)
    currency = (_value(data, "currency", "EUR") or "EUR").upper()
    amount = money_value(_value(data, "amount"))
    quote = exchange_quote(currency)
    amount_eur = to_eur(amount, currency, quote)
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO transactions (
            date, type, amount_minor, currency, amount_eur_minor, category, description, account_id,
            destination_account_id, merchant_id, status, is_credit_card_settlement,
            settlement_for_transaction_id, recurring_rule_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _value(data, "date") or today_iso(),
            _value(data, "type"),
            to_minor(amount),
            currency,
            to_minor(amount_eur),
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
    db.execute("UPDATE transactions SET exchange_rate = ?, exchange_rate_date = ?, exchange_rate_source = ? WHERE id = ?", (quote["rate"], quote["date"], quote["source"], transaction_id))
    db.execute('UPDATE transactions SET is_subscription=? WHERE id=?',(int(bool(_value(data,'is_subscription',False))),transaction_id))

    if create_settlement and _value(data, "type") == "expense" and _value(data, "status", "posted") == "posted":
        _create_credit_card_settlement(db, transaction_id, dict(data, amount_eur=amount_eur))

    return transaction_id


def update_transaction(transaction_id, data):
    with atomic(get_db()):
        _update_transaction(transaction_id, data)


def _update_transaction(transaction_id, data):
    _validate_transaction_data(data)
    currency = (_value(data, "currency", "EUR") or "EUR").upper()
    amount = money_value(_value(data, "amount"))
    db = get_db()
    old = get_transaction(transaction_id)
    if not old:
        raise ValueError("Transaction not found.")
    if amount == old["amount"] and currency == old["currency"]:
        amount_eur = old["amount_eur"]
        quote = dict(rate=old["exchange_rate"], date=old["exchange_rate_date"], source=old["exchange_rate_source"])
    else:
        quote = exchange_quote(currency)
        amount_eur = to_eur(amount, currency, quote)
    financial_change = any(str(_value(data, key, "") or "") != str(old[key] or "") for key in ("type", "date", "account_id", "destination_account_id", "status")) or amount != old["amount"] or currency != old["currency"]
    posted_settlement = db.execute("SELECT 1 FROM transactions WHERE settlement_for_transaction_id = ? AND status = 'posted'", (transaction_id,)).fetchone()
    if financial_change and db.execute("SELECT 1 FROM transaction_relationships WHERE kind='transfer_pair' AND (source_transaction_id=? OR related_transaction_id=?)",(transaction_id,transaction_id)).fetchone():
        raise ValueError("Unmatch this transfer before changing its financial details.")
    if financial_change and old['reconciled_session_id']:
        raise ValueError("This transaction is reconciled. Reopen its session before changing its financial details.")
    if financial_change and (posted_settlement or old["is_credit_card_settlement"]):
        raise ValueError("This payment has already been settled or is an automatic settlement. Record a separate correction instead.")
    refunded = db.execute("SELECT COALESCE(SUM(t.amount_eur_minor),0) / 100.0 AS total FROM transaction_links l JOIN transactions t ON t.id = l.related_transaction_id WHERE l.source_transaction_id = ? AND t.status = 'posted'", (transaction_id,)).fetchone()["total"]
    if _value(data, "type") == "expense" and to_minor(refunded) > to_minor(amount_eur):
        raise ValueError("This expense is smaller than its linked refunds. Unlink a refund first.")
    if _value(data,'type')=='income':
        link=db.execute('SELECT source_transaction_id FROM transaction_links WHERE related_transaction_id=?',(transaction_id,)).fetchone()
        if link:
            expense=get_transaction(link['source_transaction_id'])
            other=db.execute('SELECT COALESCE(SUM(t.amount_eur_minor),0) AS total FROM transaction_links l JOIN transactions t ON t.id=l.related_transaction_id WHERE l.source_transaction_id=? AND l.related_transaction_id!=?',(expense['id'],transaction_id)).fetchone()['total']
            if other+to_minor(amount_eur)>expense['amount_eur_minor']:
                raise ValueError('Linked refunds cannot exceed the original expense. Unlink this refund first.')
    splits = db.execute("SELECT id, amount_eur FROM transaction_splits WHERE transaction_id = ? ORDER BY id", (transaction_id,)).fetchall()
    if splits and _value(data, "type") == "expense" and amount_eur < 0.01 * len(splits):
        raise ValueError("This total is too small for the current split. Edit or remove the split first.")
    with atomic(db):
        db.execute(
            """
            UPDATE transactions
            SET date = ?, type = ?, amount_minor = ?, currency = ?, amount_eur_minor = ?, category = ?, description = ?,
                account_id = ?, destination_account_id = ?, merchant_id = ?,
                status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                _value(data, "date") or today_iso(), _value(data, "type"), to_minor(amount), currency, to_minor(amount_eur),
                _value(data, "category"), _value(data, "description"), _value(data, "account_id"),
                _value(data, "destination_account_id"), _value(data, "merchant_id"),
                _value(data, "status", "posted"), transaction_id,
            ),
        )
        if _value(data, "type") != "expense":
            db.execute("DELETE FROM transaction_splits WHERE transaction_id = ?", (transaction_id,))
        elif splits and old["amount_eur_minor"] != to_minor(amount_eur):
            original = sum(split["amount_eur"] for split in splits)
            allocated = 0
            for index, split in enumerate(splits[:-1]):
                remaining_lines = len(splits) - index - 1
                scaled = max(0.01, min(round(amount_eur * split["amount_eur"] / original, 2), round(amount_eur - allocated - 0.01 * remaining_lines, 2)))
                db.execute("UPDATE transaction_splits SET amount_eur_minor = ? WHERE id = ?", (to_minor(scaled), split["id"]))
                allocated += scaled
            db.execute("UPDATE transaction_splits SET amount_eur_minor = ? WHERE id = ?", (to_minor(round(amount_eur - allocated, 2)), splits[-1]["id"]))
        if _value(data, "type") != old["type"]:
            db.execute("DELETE FROM transaction_links WHERE source_transaction_id = ? OR related_transaction_id = ?", (transaction_id, transaction_id))
        db.execute("UPDATE transactions SET exchange_rate = ?, exchange_rate_date = ?, exchange_rate_source = ? WHERE id = ?", (quote["rate"], quote["date"], quote["source"], transaction_id))
        _sync_pending_settlement(db, transaction_id, data, amount_eur)
        if _value(data,'merchant_id') and _value(data,'merchant_id')!=old['merchant_id'] and old['description'] and len(old['description'])<=500:
            from money_manager.services.rules import save_alias
            save_alias(_value(data,'merchant_id'), old['description'], commit=False)


def _sync_pending_settlement(db, transaction_id, data, amount_eur):
    account = get_account(_value(data, "account_id"))
    eligible = (_value(data, "type") == "expense" and _value(data, "status", "posted") == "posted"
                and account["type"] == "credit_card" and account["settlement_account_id"])
    pending = db.execute("SELECT id FROM transactions WHERE settlement_for_transaction_id = ? AND status = 'pending'", (transaction_id,)).fetchall()
    if len(pending) > 1:
        raise ValueError("This expense has multiple settlements. Review the duplicate settlements before editing.")
    if not eligible:
        db.execute("DELETE FROM transactions WHERE settlement_for_transaction_id = ? AND status = 'pending'", (transaction_id,))
    elif pending:
        db.execute("""UPDATE transactions SET date = ?, amount_minor = ?, currency = ?, amount_eur_minor = ?,
            account_id = ?, destination_account_id = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE settlement_for_transaction_id = ? AND status = 'pending'""",
            (next_settlement_date(_value(data, "date"), account["settlement_day"]).isoformat(),
             to_minor(_value(data, "amount")), _value(data, "currency", "EUR"), to_minor(amount_eur),
             account["settlement_account_id"], account["id"],
             f"Settlement for {_value(data, 'description') or 'credit card expense'}", transaction_id))
    elif not db.execute("SELECT 1 FROM transactions WHERE settlement_for_transaction_id = ?", (transaction_id,)).fetchone():
        _create_credit_card_settlement(db, transaction_id, dict(data, amount_eur=amount_eur))


def create_settlement_for_transaction(transaction_id):
    db = get_db()
    with atomic(db):
        tx = get_transaction(transaction_id)
        if tx and tx["type"] == "expense" and tx["status"] == "posted":
            _sync_pending_settlement(db, transaction_id, tx, tx["amount_eur"])


def delete_transaction(transaction_id, commit=True):
    db = get_db()
    with (atomic(db) if commit else nullcontext()):
        if db.execute("SELECT 1 FROM transaction_relationships WHERE kind='transfer_pair' AND (source_transaction_id=? OR related_transaction_id=?)",(transaction_id,transaction_id)).fetchone():
            raise ValueError("Unmatch this transfer before deleting its original records.")
        rows = db.execute("SELECT * FROM transactions WHERE id = ? OR settlement_for_transaction_id = ? ORDER BY id", (transaction_id, transaction_id)).fetchall()
        if not rows:
            return None
        if any(row['reconciled_session_id'] for row in rows):
            raise ValueError('Reopen the reconciliation session before deleting checked transactions.')
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        details = {}
        for table in ("transaction_splits", "transaction_tags", "transaction_import_hashes", "transaction_attachments"):
            details[table] = db.execute(f"SELECT * FROM {table} WHERE transaction_id IN ({placeholders})", ids).fetchall()
        details["transaction_links"] = db.execute(f"SELECT * FROM transaction_links WHERE source_transaction_id IN ({placeholders}) OR related_transaction_id IN ({placeholders})", ids + ids).fetchall()
        details['transaction_relationships'] = db.execute(f"SELECT * FROM transaction_relationships WHERE source_transaction_id IN ({placeholders}) OR related_transaction_id IN ({placeholders})",ids+ids).fetchall()
        payload = dict(transactions=rows, details=details)
        cursor = db.execute("INSERT INTO transaction_trash (payload) VALUES (?)", (json.dumps(payload),))
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
        payload = json.loads(trash["payload"])
        rows = payload if isinstance(payload, list) else payload["transactions"]
        for row in sorted(rows, key=lambda r: bool(r["settlement_for_transaction_id"])):
            if db.execute("SELECT 1 FROM transactions WHERE id = ?", (row["id"],)).fetchone():
                raise ValueError("A transaction with this ID already exists. Nothing was restored.")
            # Removed recurring rules or merchants must not prevent recovery.
            for column, table in (("merchant_id", "merchants"), ("recurring_rule_id", "recurring_rules"), ("settlement_for_transaction_id", "transactions")):
                if row[column] and not db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row[column],)).fetchone():
                    row[column] = None
            insert_row(db, "transactions", row)
        if isinstance(payload, dict):
            for table, details in payload.get("details", {}).items():
                if table not in {"transaction_splits", "transaction_tags", "transaction_import_hashes", "transaction_links", "transaction_attachments", 'transaction_relationships'}:
                    continue
                for detail in details:
                    if table == "transaction_import_hashes" and not db.execute("SELECT 1 FROM import_batches WHERE id = ?", (detail["batch_id"],)).fetchone():
                        continue
                    if table in {'transaction_links','transaction_relationships'} and not all(db.execute("SELECT 1 FROM transactions WHERE id = ?", (detail[key],)).fetchone() for key in ("source_transaction_id", "related_transaction_id")):
                        continue
                    insert_row(db, table, detail)
        db.execute("UPDATE transaction_trash SET restored_at = CURRENT_TIMESTAMP WHERE id = ?", (trash_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise


def _validate_transaction_data(data):
    tx_type = _value(data, "type")
    status = _value(data, "status", "posted")
    amount = money_value(_value(data, "amount") or 0)
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
    from money_manager.utils.exchange import SUPPORTED_CURRENCIES
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("Choose EUR, USD, GBP, or CHF.")
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
    amount = money_value(_value(data, "amount"))
    cursor = db.execute(
        """
        INSERT INTO transactions (
            date, type, amount_minor, currency, amount_eur_minor, category, description, account_id,
            destination_account_id, merchant_id, status, is_credit_card_settlement,
            settlement_for_transaction_id
        )
        VALUES (?, 'transfer', ?, ?, ?, 'Credit card settlement', ?, ?, ?, NULL, 'pending', 1, ?)
        """,
        (
            next_settlement_date(_value(data, "date") or today_iso(), account["settlement_day"]).isoformat(),
            to_minor(amount),
            currency,
            to_minor(_value(data, "amount_eur") if _value(data, "amount_eur") is not None else to_eur(amount, currency)),
            f"Settlement for {_value(data, 'description') or 'credit card expense'}",
            account["settlement_account_id"],
            _value(data, "account_id"),
            transaction_id,
        ),
    )
    db.execute("INSERT INTO transaction_relationships(source_transaction_id,related_transaction_id,kind) VALUES(?,?,'credit_card_settlement')",(transaction_id,cursor.lastrowid))
