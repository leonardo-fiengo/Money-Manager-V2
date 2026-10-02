from collections import defaultdict
from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.services.preferences import payment_accounts
from money_manager.services.reconciliation import balance_at
from money_manager.services.transaction_details import expense_allocations
from money_manager.services.transactions import list_transactions
from money_manager.utils.money import to_minor


def account_detail(account_id, period='month', history_months=6):
    db = get_db()
    account = next((a for a in account_balances() if a['id']==account_id), None)
    if not account:
        return None
    today = date.today()
    period = period if period in {'month','last_month','year','all'} else 'month'
    from money_manager.services.analytics import dashboard_period
    window = dashboard_period(period)
    own = {r['id'] for r in db.execute('SELECT id FROM transactions WHERE account_id=?', (account_id,))}
    totals = defaultdict(int)
    for allocation in expense_allocations(window['start'], window['end']):
        if allocation['transaction_id'] in own:
            totals[allocation['category']] += to_minor(allocation['amount'])
    categories = {r['name']:r for r in db.execute('SELECT name,color FROM categories')}
    breakdown = [dict(category=k,total=v/100,color=categories.get(k,{}).get('color') or '#8da0be')
                 for k,v in sorted(totals.items(),key=lambda item:item[1],reverse=True) if v]
    monthly_spending = sum(to_minor(r['amount']) for r in expense_allocations(today.replace(day=1).isoformat(),today.isoformat()) if r['transaction_id'] in own)/100
    month_in = db.execute("""SELECT COALESCE(SUM(t.amount_eur_minor),0) AS total FROM transactions t
        WHERE t.status='posted' AND t.date BETWEEN ? AND ? AND
        ((t.account_id=? AND t.type='income' AND NOT EXISTS(SELECT 1 FROM transaction_links l WHERE l.related_transaction_id=t.id))
         OR (t.type='transfer' AND t.destination_account_id=? AND NOT EXISTS(
            SELECT 1 FROM transaction_relationships r WHERE r.kind='transfer_pair' AND r.source_transaction_id=t.id)))""",
        (today.replace(day=1).isoformat(),today.isoformat(),account_id,account_id)).fetchone()['total']/100
    top_up_source = db.execute("""SELECT a.name,a.id FROM ledger_transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.type='transfer' AND t.destination_account_id=? AND t.status='posted'
        ORDER BY t.date DESC,t.id DESC LIMIT 1""", (account_id,)).fetchone()
    settlement = db.execute('SELECT id,name FROM accounts WHERE id=?', (account['settlement_account_id'],)).fetchone()
    defaults = payment_accounts()
    history_months = history_months if history_months in {3,6,12} else 6
    import calendar
    month_index = today.year*12+today.month-1-history_months
    year, month = divmod(month_index,12)
    start = date(year,month+1,min(today.day,calendar.monthrange(year,month+1)[1]))
    history = []
    point = start
    while point < today:
        history.append(dict(date=point.isoformat(),balance=balance_at(account_id,point.isoformat())))
        point += timedelta(days=7)
    history.append(dict(date=today.isoformat(),balance=balance_at(account_id,today.isoformat())))
    return dict(account=account,recent=list_transactions(dict(account_id=account_id,account_activity=True),limit=6),
                categories=breakdown,spent=sum(totals.values())/100,monthly_spending=monthly_spending,
                month_in=month_in,top_up_source=top_up_source,settlement=settlement,
                is_default=bool(defaults and defaults[0]['id']==account_id),history=history,
                period=period,history_months=history_months)
