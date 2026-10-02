from money_manager.db.connection import get_db
from money_manager.utils.money import to_minor, money_value
from money_manager.db.atomic import atomic


def _validate_account(name, account_type, opening_balance, settlement_account_id, settlement_day, account_id=None):
    if not (name or "").strip() or len(name.strip()) > 100:
        raise ValueError("Enter an account name under 100 characters.")
    if account_type not in {"bank", "cash", "wallet", "prepaid_card", "credit_card", "investment"}:
        raise ValueError("Choose an account type.")
    money_value(opening_balance)
    if settlement_account_id:
        target = get_account(settlement_account_id)
        if not target or target["id"] == account_id or target["type"] == "credit_card":
            raise ValueError("Choose a different payment account for settlement.")
        if account_type != "credit_card":
            raise ValueError("Only credit cards can have a settlement account.")
        if not settlement_day or not 1 <= int(settlement_day) <= 28:
            raise ValueError("Enter a settlement day from 1 to 28.")


def list_accounts(active_only=True):
    sql = "SELECT * FROM accounts"
    params = []
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY type, name"
    return get_db().execute(sql, params).fetchall()


def get_account(account_id):
    return get_db().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()


def create_account(name, account_type, opening_balance=0, settlement_account_id=None, settlement_day=None, logo=None):
    _validate_account(name, account_type, opening_balance, settlement_account_id, settlement_day)
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO accounts (name, type, logo, opening_balance_minor, settlement_account_id, settlement_day)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name.strip(), account_type, logo, to_minor(opening_balance), settlement_account_id, settlement_day),
    )
    db.commit()
    return cursor.lastrowid


def update_account(account_id, name, account_type, opening_balance, settlement_account_id, settlement_day, is_active=True, logo=None):
    _validate_account(name, account_type, opening_balance, settlement_account_id, settlement_day, account_id)
    db = get_db()
    with atomic(db):
        old=get_account(account_id)
        if old and old['opening_balance_minor']!=to_minor(opening_balance) and db.execute("SELECT 1 FROM reconciliation_sessions WHERE account_id=? AND status='closed'",(account_id,)).fetchone():
            raise ValueError('Reopen this account’s reconciliation sessions before changing its opening balance.')
        _save_account(db,account_id,name,account_type,opening_balance,settlement_account_id,settlement_day,is_active,logo)


def _save_account(db,account_id,name,account_type,opening_balance,settlement_account_id,settlement_day,is_active,logo):
    db.execute(
        """
        UPDATE accounts
        SET name = ?, type = ?, logo = ?, opening_balance_minor = ?, settlement_account_id = ?,
            settlement_day = ?, is_active = ?
        WHERE id = ?
        """,
        (name.strip(), account_type, logo, to_minor(opening_balance), settlement_account_id, settlement_day, int(is_active), account_id),
    )


def _transaction_amount_eur(tx):
    stored_amount = tx["amount_eur"] if "amount_eur" in tx.keys() else None
    return float(stored_amount if stored_amount not in (None, 0) else tx["amount"])


def account_balances():
    accounts = list_accounts(active_only=False)
    balances = {account["id"]: dict(account, balance=account["opening_balance_minor"]) for account in accounts}
    rows = get_db().execute("SELECT * FROM ledger_transactions WHERE status = 'posted'").fetchall()

    for tx in rows:
        amount = tx["amount_eur_minor"]
        if tx["type"] == "income":
            balances[tx["account_id"]]["balance"] += amount
        elif tx["type"] in ("expense", "investment"):
            balances[tx["account_id"]]["balance"] -= amount
        elif tx["type"] == "transfer":
            balances[tx["account_id"]]["balance"] -= amount
            if tx["destination_account_id"] in balances:
                balances[tx["destination_account_id"]]["balance"] += amount

    for row in get_db().execute("SELECT account_id, SUM(adjustment_minor) AS amount FROM balance_checks GROUP BY account_id"):
        balances[row["account_id"]]["balance"] += row["amount"]

    for row in get_db().execute("SELECT * FROM balance_checks ORDER BY id"):
        balances[row["account_id"]]["last_check"] = row["created_at"]
        balances[row["account_id"]]["last_check_matched"] = abs(row["actual"] - row["expected"] - row["adjustment"]) < 0.005

    return [dict(row, balance=row["balance"] / 100) for row in balances.values()]
