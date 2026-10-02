from datetime import date

from money_manager.db.connection import get_db
from money_manager.services.accounts import list_accounts


def payment_preference():
    row = get_db().execute("SELECT * FROM payment_preferences WHERE id = 1").fetchone()
    return dict(row) if row else {"mode": "auto", "account_id": None}


def save_payment_preference(mode, account_id):
    if mode not in {"auto", "manual"}:
        raise ValueError("Choose automatic or manual ordering.")
    active_ids = {str(row["id"]) for row in list_accounts()}
    if mode == "manual" and str(account_id) not in active_ids:
        raise ValueError("Choose an active account as your main payment method.")
    db = get_db()
    db.execute(
        "INSERT INTO payment_preferences (id, mode, account_id) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET mode = excluded.mode, account_id = excluded.account_id",
        (mode, int(account_id) if mode == "manual" else None),
    )
    db.commit()


def payment_accounts():
    accounts = list(list_accounts())
    preference = payment_preference()
    if preference["mode"] == "manual" and any(a["id"] == preference["account_id"] for a in accounts):
        return sorted(accounts, key=lambda a: (a["id"] != preference["account_id"], a["name"].casefold()))
    # Recent purchases count more, with a 45-day half-life. Transfers and income
    # do not train payment preferences; selection stays stable while filling a form.
    scores = {a["id"]: 0 for a in accounts}
    today = date.today()
    for row in get_db().execute("SELECT account_id, date FROM ledger_transactions WHERE type = 'expense' AND status = 'posted'"):
        try:
            age = (today - date.fromisoformat(row["date"])).days
        except ValueError:
            continue
        if row["account_id"] in scores and age >= 0:
            scores[row["account_id"]] += 0.5 ** (age / 45)
    return sorted(accounts, key=lambda a: (-scores[a["id"]], a["name"].casefold()))
