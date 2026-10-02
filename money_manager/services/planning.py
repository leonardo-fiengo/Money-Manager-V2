from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.services.pending import list_pending
from money_manager.services.recurring import list_rules
from money_manager.services.pots import savings_summary, save_pot, move_pot
from money_manager.utils.dates import add_frequency


def upcoming_overview():
    today = date.today()
    end = today + timedelta(days=30)
    rows = [dict(row, source="pending") for row in list_pending() if today.isoformat() <= row["date"] <= end.isoformat()]
    existing = {(row["recurring_rule_id"], row["date"]) for row in get_db().execute("SELECT recurring_rule_id, date FROM ledger_transactions WHERE recurring_rule_id IS NOT NULL")}
    for rule in list_rules():
        if not rule["is_active"]:
            continue
        due = date.fromisoformat(rule["next_due_date"])
        while due <= end:
            if due >= today and (rule["id"], due.isoformat()) not in existing:
                rows.append(dict(date=due.isoformat(), type=rule["type"], amount=rule["amount"], amount_eur=rule["amount_eur_minor"]/100, description=rule["name"],
                                 account_name=rule["account_name"], merchant_name=rule["merchant_name"], merchant_logo=rule["merchant_logo"], source="recurring"))
            due = add_frequency(due, rule["frequency"])
    rows.sort(key=lambda r: (r["date"], r["description"] or ""))
    income = sum(r["amount_eur"] or r["amount"] for r in rows if r["type"] == "income")
    outgoing = sum(r["amount_eur"] or r["amount"] for r in rows if r["type"] in {"expense", "investment"})
    balance = sum(a["balance"] for a in account_balances())
    return dict(rows=rows, income=round(income, 2), outgoing=round(outgoing, 2), projected=round(balance + income - outgoing, 2), end=end.isoformat())
