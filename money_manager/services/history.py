import json
from datetime import date

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.utils.money import to_minor


def capture_net_worth():
    rows=account_balances()
    db=get_db()
    db.execute('INSERT INTO net_worth_snapshots(date,balance_minor,accounts_json) VALUES(?,?,?) ON CONFLICT(date) DO UPDATE SET balance_minor=excluded.balance_minor,accounts_json=excluded.accounts_json',(date.today().isoformat(),sum(to_minor(r['balance']) for r in rows),json.dumps({str(r['id']):to_minor(r['balance']) for r in rows})))
    db.commit()


def net_worth_history():
    return [dict(r,balance=r['balance_minor']/100) for r in get_db().execute('SELECT * FROM net_worth_snapshots ORDER BY date')]


WIDGET_CATALOG = (
    dict(id='position', title='Available money', description='Your balance after known commitments.', icon='accounts', width='half'),
    dict(id='actions', title='Your next moves', description='The things that deserve your attention.', icon='check', width='half'),
    dict(id='pulse', title='Income & spending', description='A quick pulse on this period.', icon='insights', width='full'),
    dict(id='upcoming', title='Coming up', description='Payments, income, and milestones ahead.', icon='calendar', width='half'),
    dict(id='budgets', title='Budget pulse', description='A little structure for everyday spending.', icon='budgets', width='half'),
    dict(id='accounts', title='Your accounts', description='Every place your money lives.', icon='accounts', width='full'),
    dict(id='cashflow', title='Cash flow', description='Six months of the bigger picture.', icon='insights', width='full'),
)


def dashboard_layout():
    catalog = {item['id']: item for item in WIDGET_CATALOG}
    row = get_db().execute('SELECT widgets_json FROM app_preferences WHERE id=1').fetchone()
    stored = json.loads(row['widgets_json']) if row else None
    if stored is None or stored == ['accounts', 'cashflow', 'upcoming', 'budgets']:
        widgets, widths = list(catalog), {}
    elif isinstance(stored, list):
        # Older settings only controlled the four supporting panels.
        widgets, widths = ['position', 'actions', 'pulse', *stored], {}
    else:
        widgets, widths = stored['widgets'], stored.get('widths', {})
    return [dict(catalog[key], width=widths.get(key, catalog[key]['width']))
            for key in dict.fromkeys(widgets) if key in catalog]


def dashboard_widgets():
    return [item['id'] for item in dashboard_layout()]


def save_widgets(widgets, widths=None):
    allowed={item['id'] for item in WIDGET_CATALOG}
    if set(widgets)-allowed: raise ValueError('Choose known dashboard widgets.')
    widths = widths or {}
    if set(widths)-set(widgets) or any(width not in {'half', 'full'} for width in widths.values()):
        raise ValueError('Choose half or full width for each widget.')
    layout = dict(version=2, widgets=list(dict.fromkeys(widgets)), widths=widths)
    db=get_db()
    db.execute('INSERT INTO app_preferences(id,widgets_json) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET widgets_json=excluded.widgets_json',(json.dumps(layout),))
    db.commit()
