"""Decision summaries composed from the ledger and existing planning services."""
from calendar import monthrange
from datetime import date, timedelta

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.services.analytics import dashboard_metrics
from money_manager.services.budgets import list_budgets
from money_manager.services.forecasting import cash_forecast
from money_manager.services.inbox import money_inbox
from money_manager.services.pots import savings_summary
from money_manager.services.preferences import payment_accounts
from money_manager.utils.money import to_minor

LIQUID_TYPES = {'bank','cash','wallet','prepaid_card'}


def planning_horizon(value):
    try:
        days = int(value)
    except (TypeError,ValueError):
        days = 30
    return days if days in {30,60,90} else 30


def month_window(value=None):
    try:
        first = date.fromisoformat((value or date.today().strftime('%Y-%m'))+'-01')
    except (TypeError,ValueError):
        first = date.today().replace(day=1)
    last = first.replace(day=monthrange(first.year,first.month)[1])
    return first.isoformat(),last.isoformat()


def cockpit_summary(days=30, include_transfer_matches=True):
    days = planning_horizon(days)
    today = date.today()
    accounts = account_balances()
    by_id = {a['id']:a for a in accounts}
    active = [a for a in accounts if a['is_active']]
    liquid = sum(to_minor(a['balance']) for a in active if a['type'] in LIQUID_TYPES)
    liabilities = sum(max(0,-to_minor(a['balance'])) for a in active if a['type']=='credit_card')
    pots = savings_summary()
    reserved = to_minor(pots['reserved'])
    forecast = cash_forecast(days)
    obligations = 0
    card_payments = {}
    new_card_costs = {}
    rows = []
    scheduled_per_account = {}
    for event in forecast['events']:
        source = by_id[event['account_id']]
        destination = by_id.get(event.get('destination_account_id'))
        # Existing card debt is reserved above. Paying it is not a second expense.
        # New card purchases count as obligations even before their settlement.
        cost = event['minor'] if source['is_active'] and source['type'] in LIQUID_TYPES | {'credit_card'} and event['type'] in {'expense','investment'} else 0
        if cost and source['type']=='credit_card':
            new_card_costs[source['id']] = new_card_costs.get(source['id'],0)+cost
        if event['type']=='transfer' and source['is_active'] and source['type'] in LIQUID_TYPES and destination:
            if destination['type']=='investment' or not destination['is_active']:
                cost = event['minor']
            elif destination['type']=='credit_card':
                card_payments[destination['id']] = card_payments.get(destination['id'],0)+event['minor']
        obligations += cost
        incoming = event['type']=='income'
        rows.append(dict(date=event['date'],due_date=event.get('due_date',event['date']),transaction_id=event.get('transaction_id'),name=event['name'],kind='income' if incoming else 'scheduled',
            label='Expected income' if incoming else 'Card settlement' if event['source']=='settlement' else 'Transfer' if event['type']=='transfer' else 'Planned payment',
            amount=event['minor']/100,sign='+' if incoming else '' if event['type']=='transfer' else '-',
            account_name=source['name'],account_id=source['id'],href='calendar.index',params={},category=None,
            type=event['type'],source=event['source'],minor=event['minor'],destination_account_id=event.get('destination_account_id')))
        for account_id in {event['account_id'],event.get('destination_account_id')} - {None}:
            scheduled_per_account.setdefault(account_id,[]).append(rows[-1])
    # Paying more than existing and newly planned debt moves extra cash into a
    # card credit balance, which is outside the liquid accounts used here.
    obligations += sum(max(0,amount-max(0,-to_minor(by_id[account_id]['balance']))-new_card_costs.get(account_id,0)) for account_id,amount in card_payments.items())
    month_end = today.replace(day=monthrange(today.year,today.month)[1])
    budgets = list_budgets()
    if month_end<=today+timedelta(days=days) and budgets:
        rows.append(dict(date=month_end.isoformat(),name='Monthly budget closes',kind='milestone',label='Budget checkpoint',amount=None,sign='',account_name='',href='budgets.index',params={}))
    for pot in pots['pots']:
        due = pot['target_date'] or pot['predicted_date']
        if due and today.isoformat()<=due<=forecast['end']:
            rows.append(dict(date=due,name=pot['name'],kind='milestone',label='Goal date' if pot['target_date'] else 'Estimated goal milestone',amount=None,sign='',account_name='',href='accounts.pots',params={}))
    rows.sort(key=lambda event:(event['date'],event['kind']=='milestone',event['name']))
    inbox = money_inbox(budgets, include_transfer_matches=include_transfer_matches)
    priorities = {'attention':0,'review':1,'upcoming':3}
    actions = sorted(inbox,key=lambda item:priorities.get(item['kind'],2))
    estimated = get_db().execute("SELECT COUNT(*) AS n FROM ledger_transactions WHERE exchange_rate_source='estimated' AND status='posted'").fetchone()['n']
    if estimated:
        actions.append(dict(kind='review',title=f'Review {estimated} estimated exchange rate'+('s' if estimated!=1 else ''),detail='Compare the saved conversion with your statement.',href='transactions.index',params={'view':'review'}))
    unchecked = [a for a in active if not a.get('last_check')]
    if unchecked:
        actions.append(dict(kind='review',title=f'Check {len(unchecked)} account balance'+('s' if len(unchecked)!=1 else ''),detail='A quick reality check for your money.',href='accounts.check'))
    for pot in pots['pots']:
        if pot['unattributed']>0:
            actions.append(dict(kind='review',title=f"Give {pot['name']} a funding source",detail='Choose where the reserved money comes from.',href='accounts.pots'))
        elif pot['reserved']>=pot['target']:
            actions.append(dict(kind='upcoming',title=f"{pot['name']}: goal reached",detail='Spend it when you actually make the purchase.',href='accounts.pots'))
    available = liquid-reserved-liabilities-obligations
    actions.sort(key=lambda item:priorities.get(item['kind'],2))
    attention = sum(item['kind']=='attention' for item in actions)
    state = 'action' if available<0 or attention else 'review' if actions else 'good'
    if not active:
        headline,explanation = 'Give your money a place to live.', 'Add an account, then record or import your first transactions.'
        actions = [dict(kind='review',title='Add your first account',detail='Start with the bank, card, or wallet you use most.',href='accounts.new')]
        state='review'
    elif available<0:
        headline,explanation = 'Your planned money is a little stretched.', f'Planned payments, card debt, and savings reservations exceed available cash by €{abs(available)/100:,.2f}.'
    elif actions:
        headline = f"{len(actions)} thing{'s' if len(actions)!=1 else ''} to check. You've got this."
        explanation = f'€{available/100:,.2f} remains after savings, card debt, and the next {days} days of planned outgoing payments.'
    else:
        headline,explanation = "You're on track this month.", f'€{available/100:,.2f} remains after your known commitments for the next {days} days.'
    account_reserved = {r['account_id']:r['reserved'] for r in get_db().execute("""SELECT s.account_id,SUM(s.reserved_minor) AS reserved FROM pot_sources s
        JOIN savings_pots p ON p.id=s.pot_id WHERE p.spent_at IS NULL AND p.deleted_at IS NULL GROUP BY s.account_id""")}
    preference_order = {a['id']:i for i,a in enumerate(payment_accounts())}
    account_rows = []
    for account in accounts:
        amount = account_reserved.get(account['id'],0)
        upcoming = scheduled_per_account.get(account['id'],[])
        role = 'archived' if not account['is_active'] else 'credit' if account['type']=='credit_card' else 'investments' if account['type']=='investment' else 'savings' if account.get('role')=='savings' else 'everyday'
        account_rows.append(dict(account,role_group=role,reserved=amount/100,available=(to_minor(account['balance'])-amount)/100,
            upcoming=upcoming,next_movement=upcoming[0] if upcoming else None,
            warning='Reservation exceeds balance' if amount>max(0,to_minor(account['balance'])) else 'Check balance difference' if account.get('last_check') and not account.get('last_check_matched') else None))
    account_rows.sort(key=lambda a:preference_order.get(a['id'],999))
    return dict(days=days,state=state,headline=headline,explanation=explanation,available=available/100,
        liquid=liquid/100,total=sum(to_minor(a['balance']) for a in active)/100,reserved=reserved/100,
        card_debt=liabilities/100,bills=obligations/100,actions=actions,top_actions=actions[:3],
        timeline=rows,budgets=budgets,pots=pots['pots'],accounts=account_rows,forecast=forecast)


def plan_summary(month=None,days=30):
    cockpit = cockpit_summary(days)
    start,end = month_window(month)
    metrics = dashboard_metrics(start,end)
    budgets = list_budgets(start[:7])
    # Only unpaid future activity appears in the planned column.
    forecast = cockpit['forecast'] if end<=cockpit['forecast']['end'] else cash_forecast(365)
    events = [e for e in forecast['events'] if start<=e['date']<=end]
    expected_income = sum(e['minor'] for e in events if e['type']=='income')
    planned = sum(e['minor'] for e in events if e['type'] in {'expense','investment'})
    db=get_db()
    planned_categories = {}
    for e in events:
        if e['type']=='expense':
            category=e.get('category')
            if category:
                planned_categories[category]=planned_categories.get(category,0)+e['minor']
    flexible = sum(max(0,to_minor(b['available_amount'])-to_minor(b['spent_amount'])-planned_categories.get(b['category_name'],0)) for b in budgets)
    goal_net = db.execute("SELECT COALESCE(SUM(m.delta_minor),0) AS total FROM pot_movements m JOIN savings_pots p ON p.id=m.pot_id WHERE substr(m.created_at,1,7)=? AND p.deleted_at IS NULL AND p.spent_at IS NULL",(start[:7],)).fetchone()['total']
    actual_out = to_minor(metrics['expenses'])+to_minor(metrics['investments'])
    income = to_minor(metrics['income'])+expected_income
    return dict(cockpit=cockpit,month=start[:7],month_label=date.fromisoformat(start).strftime('%B %Y'),days=cockpit['days'],
        metrics=metrics,budgets=budgets,income=income/100,actual_out=actual_out/100,planned=planned/100,
        flexible=flexible/100,goal_contributions=max(0,goal_net)/100,
        remainder=(income-actual_out-planned-flexible-max(0,goal_net))/100)
