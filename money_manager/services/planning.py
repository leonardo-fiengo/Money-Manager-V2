from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.services.pending import list_pending
from money_manager.services.recurring import list_rules
from money_manager.services.reconciliation import money_value
from money_manager.utils.dates import add_frequency


def upcoming_overview():
    today = date.today()
    end = today + timedelta(days=30)
    rows = [dict(row, source="pending") for row in list_pending() if today.isoformat() <= row["date"] <= end.isoformat()]
    existing = {(row["recurring_rule_id"], row["date"]) for row in get_db().execute("SELECT recurring_rule_id, date FROM transactions WHERE recurring_rule_id IS NOT NULL")}
    for rule in list_rules():
        if not rule["is_active"]:
            continue
        due = date.fromisoformat(rule["next_due_date"])
        while due <= end:
            if due >= today and (rule["id"], due.isoformat()) not in existing:
                rows.append(dict(date=due.isoformat(), type=rule["type"], amount=rule["amount"], amount_eur=rule["amount"], description=rule["name"],
                                 account_name=rule["account_name"], merchant_name=rule["merchant_name"], merchant_logo=rule["merchant_logo"], source="recurring"))
            due = add_frequency(due, rule["frequency"])
    rows.sort(key=lambda r: (r["date"], r["description"] or ""))
    income = sum(r["amount_eur"] or r["amount"] for r in rows if r["type"] == "income")
    outgoing = sum(r["amount_eur"] or r["amount"] for r in rows if r["type"] in {"expense", "investment"})
    balance = sum(a["balance"] for a in account_balances())
    return dict(rows=rows, income=round(income, 2), outgoing=round(outgoing, 2), projected=round(balance + income - outgoing, 2), end=end.isoformat())


def savings_summary():
    pots = [dict(r) for r in get_db().execute("SELECT * FROM savings_pots ORDER BY id")]
    reserved = round(sum(p["reserved"] for p in pots), 2)
    balance = round(sum(a["balance"] for a in account_balances() if a["type"] != "investment"), 2)
    return dict(pots=pots, reserved=reserved, balance=balance, unassigned=round(balance - reserved, 2))


def save_pot(name, target, reserved, pot_id=None):
    name = (name or "").strip()
    target, reserved = money_value(target), money_value(reserved)
    if not name or len(name) > 100 or target <= 0 or reserved < 0:
        raise ValueError("Enter a name, a positive target, and a nonnegative reserved amount.")
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT * FROM savings_pots WHERE id = ?", (pot_id,)).fetchone() if pot_id else None
        if pot_id and not old:
            raise ValueError("Savings pot not found.")
        old_reserved = old["reserved"] if old else 0
        summary = savings_summary()
        if reserved > old_reserved and summary["reserved"] - old_reserved + reserved > max(0, summary["balance"]) + 0.005:
            raise ValueError("There isn't enough unassigned money. Lower the reserved amount or release money from another pot.")
        if pot_id:
            db.execute("UPDATE savings_pots SET name = ?, target = ?, reserved = ? WHERE id = ?", (name, target, reserved, pot_id))
        else:
            db.execute("INSERT INTO savings_pots (name, target, reserved) VALUES (?, ?, ?)", (name, target, reserved))
        db.commit()
    except Exception:
        db.rollback()
        raise
