from decimal import Decimal, InvalidOperation
from uuid import uuid4

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances


def money_value(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal('999999999'):
            raise ValueError
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError
        return float(amount)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid balance with at most two decimal places.") from None


def preview_balances(values):
    rows = []
    db = get_db()
    for account in account_balances():
        value = values.get(str(account["id"]), "")
        if not str(value).strip():
            continue
        actual = money_value(value)
        delta = round(actual - account["balance"], 2)
        hints = []
        pending = db.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE status = 'pending' AND (account_id = ? OR destination_account_id = ?)",
            (account["id"], account["id"]),
        ).fetchone()["count"]
        if pending:
            hints.append(f"{pending} pending payment(s) are excluded from the app balance. Compare with your bank's booked balance, before pending holds.")
        duplicates = db.execute(
            "SELECT COUNT(*) AS count FROM (SELECT date, amount_eur, type, merchant_id, description FROM transactions "
            "WHERE account_id = ? AND status = 'posted' GROUP BY date, amount_eur, type, merchant_id, description HAVING COUNT(*) > 1)",
            (account["id"],),
        ).fetchone()["count"]
        if delta and duplicates:
            hints.append(f"{duplicates} group(s) of similar entries could be duplicates. Review them before adjusting.")
        if delta:
            hints.append("A missing expense or an overstated income could explain this." if delta < 0 else "A missing income or an extra expense could explain this.")
        rows.append(dict(account, actual=actual, difference=delta, hints=hints))
    if not rows:
        raise ValueError("Enter an actual balance for at least one account.")
    for row in rows:
        matches = [other["name"] for other in rows if other["id"] != row["id"] and row["difference"] and abs(other["difference"] + row["difference"]) < 0.005]
        if matches:
            row["hints"].insert(0, f"An opposite difference in {', '.join(matches)} could mean a payment used the wrong account or a transfer is missing.")
    return rows


def check_payload(rows):
    return {"batch_id": str(uuid4()), "rows": [
        {"id": r["id"], "expected": r["balance"], "actual": r["actual"]} for r in rows
    ]}


def record_checks(payload, adjust_ids, note):
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM balance_checks WHERE batch_id = ?", (payload["batch_id"],)).fetchone():
            raise ValueError("This balance check has already been saved.")
        balances = {a["id"]: a for a in account_balances()}
        allowed = {str(r["id"]) for r in payload["rows"]}
        if not set(adjust_ids).issubset(allowed):
            raise ValueError("Invalid adjustment selection. Check balances again.")
        for row in payload["rows"]:
            account = balances.get(row["id"])
            if not account or abs(account["balance"] - row["expected"]) > 0.005:
                raise ValueError("An account balance changed since this preview. Check balances again before saving.")
            delta = round(row["actual"] - row["expected"], 2) if str(row["id"]) in adjust_ids else 0
            db.execute(
                "INSERT INTO balance_checks (account_id, expected, actual, adjustment, note, batch_id) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["expected"], row["actual"], delta, note.strip()[:500], payload["batch_id"]),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


def check_history():
    return get_db().execute(
        "SELECT b.*, a.name AS account_name FROM balance_checks b JOIN accounts a ON a.id = b.account_id ORDER BY b.id DESC LIMIT 50"
    ).fetchall()
