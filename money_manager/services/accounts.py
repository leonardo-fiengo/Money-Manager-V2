from money_manager.db.connection import get_db


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
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO accounts (name, type, logo, opening_balance, settlement_account_id, settlement_day)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, account_type, logo, opening_balance, settlement_account_id, settlement_day),
    )
    db.commit()
    return cursor.lastrowid


def update_account(account_id, name, account_type, opening_balance, settlement_account_id, settlement_day, is_active=True, logo=None):
    db = get_db()
    db.execute(
        """
        UPDATE accounts
        SET name = ?, type = ?, logo = ?, opening_balance = ?, settlement_account_id = ?,
            settlement_day = ?, is_active = ?
        WHERE id = ?
        """,
        (name, account_type, logo, opening_balance, settlement_account_id, settlement_day, int(is_active), account_id),
    )
    db.commit()


def _transaction_amount_eur(tx):
    stored_amount = tx["amount_eur"] if "amount_eur" in tx.keys() else None
    return float(stored_amount if stored_amount not in (None, 0) else tx["amount"])


def account_balances():
    accounts = list_accounts(active_only=False)
    balances = {account["id"]: dict(account, balance=account["opening_balance"]) for account in accounts}
    rows = get_db().execute("SELECT * FROM transactions WHERE status = 'posted'").fetchall()

    for tx in rows:
        amount = _transaction_amount_eur(tx)
        if tx["type"] == "income":
            balances[tx["account_id"]]["balance"] += amount
        elif tx["type"] in ("expense", "investment"):
            balances[tx["account_id"]]["balance"] -= amount
        elif tx["type"] == "transfer":
            balances[tx["account_id"]]["balance"] -= amount
            if tx["destination_account_id"] in balances:
                balances[tx["destination_account_id"]]["balance"] += amount

    return [dict(row, balance=round(row["balance"], 2)) for row in balances.values()]
