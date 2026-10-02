from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.budgets import list_budgets
from money_manager.services.planning import upcoming_overview


def money_inbox(budgets=None, upcoming=None):
    db = get_db()
    items = []
    recent_checks = db.execute("""
        SELECT b.*, a.name AS account_name FROM balance_checks b
        JOIN accounts a ON a.id = b.account_id
        WHERE b.id IN (SELECT MAX(id) FROM balance_checks GROUP BY account_id)
    """).fetchall()
    for check in recent_checks:
        difference = round(check["actual"] - check["expected"] - check["adjustment"], 2)
        if abs(difference) >= 0.01:
            items.append(dict(kind="attention", title=f'{check["account_name"]} balance differs by €{abs(difference):.2f}', detail="Review your balance check", href="accounts.check"))
    uncategorized = db.execute("""
        SELECT COUNT(*) AS count FROM ledger_transactions t
        JOIN transaction_import_hashes h ON h.transaction_id = t.id
        WHERE t.category IS NULL AND t.type = 'expense'
    """).fetchone()["count"]
    if uncategorized:
        items.append(dict(kind="review", title=f"{uncategorized} imported transactions need categories", detail="Review transactions", href="transactions.index", params=dict(needs_category=1)))
    for budget in (budgets if budgets is not None else list_budgets()):
        if budget["spent_amount"] > budget["available_amount"] + 0.01:
            excess = budget["spent_amount"] - budget["available_amount"]
            items.append(dict(kind="attention", title=f'{budget["category_name"]} budget exceeded by €{excess:.2f}', detail="Review spending", href="budgets.index"))
        elif budget["projected"] > budget["available_amount"] + 0.01:
            excess = budget["projected"] - budget["available_amount"]
            items.append(dict(kind="attention", title=f'{budget["category_name"]} may exceed budget by €{excess:.2f}', detail="See spending pace", href="budgets.index"))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for event in (upcoming if upcoming is not None else upcoming_overview())["rows"]:
        if event["date"] == tomorrow and event["type"] == "expense" and event["source"] == "recurring":
            items.append(dict(kind="upcoming", title=f'{event["description"]} expected tomorrow', detail=f'€{event["amount_eur"] or event["amount"]:.2f}', href="recurring.index"))
    from money_manager.services.subscriptions import detected_subscriptions
    from money_manager.services.relationships import transfer_candidates
    suggestions=detected_subscriptions()
    if suggestions:
        items.append(dict(kind='review',title=f'{len(suggestions)} possible subscriptions',detail='Review repeated payments before tracking them',href='recurring.subscriptions'))
    for suggestion in suggestions:
        if suggestion['price_increase']:
            items.append(dict(kind='attention',title=f"{suggestion['name']} increased by €{suggestion['price_increase']:.2f}",detail='Review the last price and upcoming payment',href='recurring.subscriptions'))
    for row in db.execute("SELECT l.*,COALESCE((SELECT SUM(p.amount_minor) FROM loan_payments p WHERE p.loan_id=l.id),0) AS paid FROM loans l WHERE l.status='open' AND l.due_date<?",(date.today().isoformat(),)):
        if row['expected_total_amount_minor']>row['paid']:
            items.append(dict(kind='attention',title=f"{row['counterparty']} loan is overdue",detail='Review repayments and the due date',href='loans.detail',params=dict(loan_id=row['id'])))
    duplicates=db.execute("SELECT date,account_id,description,COUNT(*) AS count FROM ledger_transactions WHERE status='posted' AND type!='transfer' GROUP BY date,account_id,type,amount_eur_minor,COALESCE(merchant_id,0),COALESCE(description,'') HAVING COUNT(*)>1 ORDER BY date DESC LIMIT 10").fetchall()
    for row in duplicates:
        items.append(dict(kind='review',title=f"{row['count']} similar payments on {row['date']}",detail='Compare the entries before deleting anything',href='transactions.index',params=dict(account_id=row['account_id'],start=row['date'],end=row['date'])))
    candidates=transfer_candidates()
    if candidates: items.append(dict(kind='review',title=f'{len(candidates)} possible transfer matches',detail='Review both entries and merge matching movements',href='finance.transfers'))
    recent=(date.today()-timedelta(days=30)).isoformat()
    for row in db.execute("SELECT t.*,m.name AS merchant_name FROM ledger_transactions t LEFT JOIN merchants m ON m.id=t.merchant_id WHERE t.type='expense' AND t.status='posted' AND t.date>=? AND t.merchant_id IS NOT NULL AND t.amount_eur_minor>=5000 ORDER BY t.date DESC LIMIT 100",(recent,)):
        baseline=db.execute("SELECT COUNT(*) AS count,AVG(amount_eur_minor) AS average FROM ledger_transactions WHERE type='expense' AND status='posted' AND merchant_id=? AND date<?",(row['merchant_id'],recent)).fetchone()
        if baseline['count']>=5 and row['amount_eur_minor']>3*baseline['average']:
            items.append(dict(kind='attention',title=f"Unusually large payment to {row['merchant_name']}",detail='More than three times your earlier average',href='transactions.details',params=dict(transaction_id=row['id'])))
    from money_manager.services.subscriptions import latest_subscription_payment
    for rule in db.execute('SELECT * FROM recurring_rules WHERE is_subscription=1 AND is_active=1'):
        latest=latest_subscription_payment(rule)
        if latest and latest['amount_minor']!=rule['amount_minor']:
            items.append(dict(kind='attention',title=f"{rule['name']} subscription price changed",detail=f"{rule['currency']} {rule['amount']:.2f} → {latest['amount']:.2f}; review the next amount",href='recurring.edit',params=dict(rule_id=rule['id'])))
    for row in db.execute("SELECT r.id,r.name,r.amount_minor,t.amount_minor AS latest_amount FROM recurring_rules r JOIN ledger_transactions t ON t.id=(SELECT id FROM ledger_transactions WHERE recurring_rule_id=r.id AND currency=r.currency AND status='posted' ORDER BY date DESC,id DESC LIMIT 1) WHERE r.is_subscription=0 AND r.is_active=1 AND t.amount_minor!=r.amount_minor"):
        items.append(dict(kind='attention',title=f"{row['name']} recurring amount changed",detail='Review the next scheduled amount',href='recurring.edit',params=dict(rule_id=row['id'])))
    return items
