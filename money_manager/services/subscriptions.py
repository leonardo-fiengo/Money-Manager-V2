from collections import defaultdict
from datetime import date
from statistics import median

from money_manager.db.connection import get_db
from money_manager.services.rules import normalized
from money_manager.utils.dates import add_frequency


def detected_subscriptions():
    groups=defaultdict(list)
    for row in get_db().execute("SELECT t.*,m.name AS merchant_name,a.name AS account_name FROM ledger_transactions t LEFT JOIN merchants m ON m.id=t.merchant_id JOIN accounts a ON a.id=t.account_id WHERE t.type='expense' AND t.status='posted' AND t.recurring_rule_id IS NULL ORDER BY t.date,t.id"):
        key=(row['account_id'],row['merchant_id'] or normalized(row['description']),row['currency'])
        if key[1]: groups[key].append(row)
    results=[]
    for rows in groups.values():
        if len(rows)<2: continue
        intervals=[(date.fromisoformat(b['date'])-date.fromisoformat(a['date'])).days for a,b in zip(rows,rows[1:])][-5:]
        period=median(intervals)
        frequency=next((name for name,low,high in [('weekly',5,9),('monthly',25,35),('yearly',350,380)] if low<=period<=high and all(low<=i<=high for i in intervals)),None)
        if not frequency or (frequency!='yearly' and len(rows)<3): continue
        baseline=int(median(r['amount_minor'] for r in rows[-4:-1]))
        latest=rows[-1]
        if (date.today()-date.fromisoformat(latest['date'])).days>{'weekly':20,'monthly':70,'yearly':550}[frequency]: continue
        if not baseline or any(abs(r['amount_minor']-baseline)>max(500,baseline*.3) for r in rows[-4:]): continue
        name=latest['merchant_name'] or latest['description']
        if get_db().execute('SELECT 1 FROM recurring_rules WHERE is_active=1 AND account_id=? AND (merchant_id=? OR lower(name)=lower(?))',(latest['account_id'],latest['merchant_id'],name)).fetchone(): continue
        factor={'weekly':52/12,'monthly':1,'yearly':1/12}[frequency]
        due=add_frequency(latest['date'],frequency)
        while due<date.today(): due=add_frequency(due,frequency)
        results.append(dict(latest,name=name,frequency=frequency,next_due_date=due.isoformat(),monthly_cost=round(latest['amount']*factor,2),annual_cost=round(latest['amount']*factor*12,2),previous_amount=baseline/100,price_increase=max(0,latest['amount_minor']-baseline)/100,occurrences=len(rows)))
    return sorted(results,key=lambda r:(-r['price_increase'],-r['monthly_cost']))


def track_subscription(transaction_id):
    from money_manager.services.recurring import create_rule
    candidate=next((r for r in detected_subscriptions() if r['id']==int(transaction_id)),None)
    if not candidate: raise ValueError('This suggestion is no longer available. Refresh and review the detected payments.')
    return create_rule(dict(name=candidate['name'],type='expense',amount=candidate['amount'],currency=candidate['currency'],account_id=candidate['account_id'],merchant_id=candidate['merchant_id'],category=candidate['category'],frequency=candidate['frequency'],next_due_date=candidate['next_due_date'],is_subscription=True))


def latest_subscription_payment(rule):
    return get_db().execute("""SELECT * FROM ledger_transactions WHERE type='expense' AND status='posted' AND account_id=? AND currency=?
        AND (recurring_rule_id=? OR (merchant_id IS NOT NULL AND merchant_id=?) OR (merchant_id IS NULL AND lower(description) IN(lower(?),lower(?))))
        ORDER BY date DESC,id DESC LIMIT 1""",(rule['account_id'],rule['currency'],rule['id'],rule['merchant_id'],rule['name'],rule['description'] or rule['name'])).fetchone()
