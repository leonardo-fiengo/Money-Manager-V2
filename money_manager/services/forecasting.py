from collections import defaultdict
from datetime import date, timedelta
import json

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.services.recurring import list_rules
from money_manager.services.transaction_details import expense_allocations
from money_manager.utils.dates import add_frequency
from money_manager.utils.money import to_minor


def list_scenarios():
    return get_db().execute('SELECT * FROM forecast_scenarios ORDER BY name').fetchall()


def save_scenario(name,income=0,spending=0,investment=0):
    name=(name or '').strip()
    if not name or len(name)>100: raise ValueError('Choose a scenario name under 100 characters.')
    values=[to_minor(value or 0) for value in (income,spending,investment)]
    db=get_db()
    db.execute('INSERT INTO forecast_scenarios(name,income_delta_minor,spending_delta_minor,investment_delta_minor) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET income_delta_minor=excluded.income_delta_minor,spending_delta_minor=excluded.spending_delta_minor,investment_delta_minor=excluded.investment_delta_minor',(name,*values))
    db.commit()


def cash_forecast(days=30,scenario_id=None):
    try: days=int(days)
    except (TypeError,ValueError): days=30
    if days not in {30,60,90,180,365}: days=30
    today=date.today(); end=today+timedelta(days=days); db=get_db()
    accounts=account_balances()
    balances={a['id']:to_minor(a['balance']) for a in accounts}
    opening=sum(balances.values())
    history_start=(today-timedelta(days=90)).isoformat()
    recurring_ids={r['id'] for r in db.execute('SELECT id FROM ledger_transactions WHERE recurring_rule_id IS NOT NULL OR is_credit_card_settlement=1 OR is_subscription=1')}
    daily_spend=round(sum(to_minor(r['amount']) for r in expense_allocations(history_start,today.isoformat()) if r['transaction_id'] not in recurring_ids)/90)
    scenario=db.execute('SELECT * FROM forecast_scenarios WHERE id=?',(scenario_id,)).fetchone() if scenario_id else None
    adjustment=round((scenario['income_delta_minor']-scenario['spending_delta_minor']-scenario['investment_delta_minor'])/30.4375) if scenario else 0
    events=defaultdict(list); existing=set()
    for tx in db.execute("SELECT * FROM ledger_transactions WHERE status='pending' AND date<=?",(end.isoformat(),)):
        if tx['recurring_rule_id']: existing.add((tx['recurring_rule_id'],tx['date']))
        when=max(tx['date'],(today+timedelta(days=1)).isoformat())
        events[when].append(dict(date=when,name=tx['description'] or tx['category'] or tx['type'].title(),minor=tx['amount_eur_minor'],type=tx['type'],account_id=tx['account_id'],destination_account_id=tx['destination_account_id'],source='pending'))
        account=next(a for a in accounts if a['id']==tx['account_id'])
        if tx['type']=='expense' and account['type']=='credit_card' and account['settlement_account_id'] and not db.execute('SELECT 1 FROM transactions WHERE settlement_for_transaction_id=?',(tx['id'],)).fetchone():
            from money_manager.utils.dates import next_settlement_date
            settlement=max(next_settlement_date(tx['date'],account['settlement_day']).isoformat(),when)
            if settlement<=end.isoformat():
                events[settlement].append(dict(date=settlement,name='Card settlement: '+(tx['description'] or 'Pending purchase'),minor=tx['amount_eur_minor'],type='transfer',account_id=account['settlement_account_id'],destination_account_id=account['id'],source='settlement'))
    for rule in list_rules():
        if not rule['is_active']: continue
        due=date.fromisoformat(rule['next_due_date'])
        while due<=end:
            if due>=today and (rule['id'],due.isoformat()) not in existing:
                when=max(due.isoformat(),(today+timedelta(days=1)).isoformat())
                events[when].append(dict(date=when,name=rule['name'],minor=rule['amount_eur_minor'],type=rule['type'],account_id=rule['account_id'],destination_account_id=None,source='recurring'))
                account=next(a for a in accounts if a['id']==rule['account_id'])
                if rule['type']=='expense' and account['type']=='credit_card' and account['settlement_account_id']:
                    from money_manager.utils.dates import next_settlement_date
                    settlement=max(next_settlement_date(due.isoformat(),account['settlement_day']).isoformat(),when)
                    if settlement<=end.isoformat(): events[settlement].append(dict(date=settlement,name='Card settlement: '+rule['name'],minor=rule['amount_eur_minor'],type='transfer',account_id=account['settlement_account_id'],destination_account_id=account['id'],source='settlement'))
            due=add_frequency(due,rule['frequency'])
    balance=opening; curve=[dict(date=today.isoformat(),balance=balance/100)]; event_rows=[]
    for offset in range(1,days+1):
        when=(today+timedelta(days=offset)).isoformat()
        for event in events[when]:
            delta=event['minor']*(1 if event['type']=='income' else -1)
            balances[event['account_id']]+=delta
            if event['type']=='transfer':
                balances[event['destination_account_id']]+=event['minor']; delta=0
            balance+=delta
            event_rows.append(dict(event,amount=delta/100,balance=balance/100,transfer_amount=event['minor']/100))
        balance+=adjustment-daily_spend
        curve.append(dict(date=when,balance=balance/100))
    return dict(days=days,today=today.isoformat(),end=end.isoformat(),opening=opening/100,projected=balance/100,daily_spend=daily_spend/100,curve=curve,events=event_rows,scenario=scenario,scenario_daily=adjustment/100,accounts=[dict(a,scheduled_balance=balances[a['id']]/100) for a in accounts])
