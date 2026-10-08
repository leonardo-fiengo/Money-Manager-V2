"""Read-only presentation summaries for the financial overview.

Balances use the same signed EUR ledger as Accounts, including archived accounts
and card liabilities. Opening balances have no effective date in the schema;
they form the baseline rather than invented income at account creation.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from money_manager.db.connection import get_db
from money_manager.services.analytics import cumulative_balance, dashboard_metrics, monthly_summary
from money_manager.services.cockpit import cockpit_summary
from money_manager.services.transactions import list_transactions
from money_manager.utils.money import to_minor


def balance_series(period='3m', today=None):
    today = today or date.today()
    period = period if period in {'1w', '1m', '3m', '1y', 'all'} else '3m'
    db = get_db()
    baseline = db.execute('SELECT COALESCE(SUM(opening_balance_minor),0) AS total, MIN(substr(created_at,1,10)) AS first FROM accounts').fetchone()
    history = cumulative_balance()
    first = min([today.isoformat(), baseline['first'] or today.isoformat(), *[r['date'] for r in history]])
    if period == 'all':
        start = date.fromisoformat(first) - timedelta(days=1)
    elif period == '1w':
        start = today - timedelta(days=7)
    else:
        months = {'1m': 1, '3m': 3, '1y': 12}[period]
        index = today.year * 12 + today.month - 1 - months
        year, month = divmod(index, 12)
        start = date(year, month + 1, min(today.day, monthrange(year, month + 1)[1]))
    opening = baseline['total']
    for row in history:
        if row['date'] <= start.isoformat():
            opening = to_minor(row['balance'])
    points = [dict(date=start.isoformat(), balance=opening / 100)]
    points.extend(row for row in history if start.isoformat() < row['date'] <= today.isoformat())
    current = to_minor(history[-1]['balance']) if history else baseline['total']
    has_future = any(row['date'] > today.isoformat() for row in history)
    # The live ledger counts posted events regardless of date. Never conceal an
    # imported future-posted event by drawing a fictitious point at today's date.
    if not has_future and points[-1]['date'] != today.isoformat():
        points.append(dict(date=today.isoformat(), balance=current / 100))
    change = current - opening
    return dict(period=period, points=points, total=current / 100,
                change=change / 100, percent=round(change / opening * 100, 1) if opening > 0 else None,
                start=start.isoformat(), end=today.isoformat(), has_future=has_future,
                has_accounts=bool(db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone()))


def percent_change(current, previous):
    return round((current - previous) / abs(previous) * 100, 1) if previous else None


def flow_summary(months=6, today=None):
    today = today or date.today()
    months = months if months in {3, 6, 12} else 6
    index = today.year * 12 + today.month - 1
    keys = [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(index - 2 * months + 1, index + 1)]
    amounts = {r['month']: r for r in monthly_summary(keys[0] + '-01', today.isoformat())}
    rows = [dict(amounts.get(key, dict(month=key, income=0, expenses=0, investments=0))) for key in keys]
    for row in rows:
        row['net'] = round(row['income'] - row['expenses'] - row['investments'], 2)
        row['label'] = date.fromisoformat(row['month'] + '-01').strftime('%b %y')
    averages, comparisons = {}, {}
    for metric in ('income', 'expenses', 'net'):
        current = sum(to_minor(r[metric]) for r in rows[months:]) / (100 * months)
        previous = sum(to_minor(r[metric]) for r in rows[:months]) / (100 * months)
        averages[metric] = round(current, 2)
        comparisons[metric] = percent_change(current, previous)
    return dict(months=months, rows=rows[months:], averages=averages, comparisons=comparisons)


def overview_summary():
    today = date.today()
    start = today.replace(day=1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    previous_end = previous_start.replace(day=min(today.day, previous_end.day))
    metrics = dashboard_metrics(start.isoformat(), today.isoformat())
    previous = dashboard_metrics(previous_start.isoformat(), previous_end.isoformat())
    # Full transfer matching stays in Money Inbox. Its ledger self-join is not
    # needed for the overview's three short insights on every dashboard load.
    cockpit = cockpit_summary(30, include_transfer_matches=False)
    comparisons = {key: percent_change(metrics[key], previous[key]) for key in ('income', 'expenses')}
    comparisons['savings_rate'] = round(metrics['savings_rate'] - previous['savings_rate'], 1) if metrics['income'] and previous['income'] else None
    accounts = [a for a in cockpit['accounts'] if a['is_active']]
    upcoming = [r for r in cockpit['timeline'] if r.get('amount') is not None and
                (r.get('type') in {'expense', 'investment'} or r.get('source') == 'settlement')]
    upcoming = sorted([dict(r,date=r.get('due_date',r['date']),overdue=r.get('due_date',r['date']) < today.isoformat()) for r in upcoming],key=lambda r:(r['date'],r['name']))[:5]
    insights = [dict(a) for a in cockpit['actions'] if a['kind'] in {'attention', 'review'}]
    # Replace conversational balance-check copy with an explicit factual scope.
    for item in insights:
        if item['href'] == 'accounts.check' and item['kind'] == 'review':
            item['detail'] = 'These accounts have no saved balance check.'
    stale = sum(bool(a.get('last_check')) and a['last_check'][:10] < (today - timedelta(days=30)).isoformat() for a in accounts)
    if stale:
        insights.insert(0, dict(kind='review', title=f'{stale} balance check'+('s' if stale != 1 else '')+' older than 30 days',
                               detail='Compare the recorded balance with a recent statement.', href='accounts.check'))
    try:
        hour = datetime.now(ZoneInfo('Europe/Rome')).hour
    except ZoneInfoNotFoundError:
        hour = datetime.now().hour
    greeting = 'Good morning' if hour < 12 else 'Good afternoon' if hour < 18 else 'Good evening'
    # Tax and loan trackers do not link their unpaid balances to forecast rows.
    # Summing both could double count a scheduled payment, so ask for review
    # instead of presenting an unreliable safe-to-spend number.
    horizon = (today + timedelta(days=30)).isoformat()
    unlinked_due = get_db().execute('''SELECT COUNT(*) AS n FROM taxes t WHERE due_date<=?
        AND amount_minor>COALESCE((SELECT SUM(amount_minor) FROM tax_payments p WHERE p.tax_id=t.id),0)''', (horizon,)).fetchone()['n']
    unlinked_due += get_db().execute('''SELECT COUNT(*) AS n FROM loans l WHERE direction='borrowed' AND status='open'
        AND due_date<=? AND expected_total_amount_minor>COALESCE((SELECT SUM(amount_minor) FROM loan_payments p WHERE p.loan_id=l.id),0)''', (horizon,)).fetchone()['n']
    return dict(metrics=metrics, previous=previous, comparisons=comparisons, accounts=accounts,
                cockpit=cockpit, upcoming=upcoming, insights=insights[:3],
                recent=list_transactions(limit=5), history=balance_series(), flow=flow_summary(),
                today=today.isoformat(), date_label=today.strftime('%a, %d %b %Y'),
                month_label=today.strftime('%B %Y'), greeting=greeting, start=start.isoformat(),
                safe_available=cockpit['available'] if accounts and not unlinked_due else None,
                unlinked_due=unlinked_due)
