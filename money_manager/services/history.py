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


def dashboard_widgets():
    row=get_db().execute('SELECT widgets_json FROM app_preferences WHERE id=1').fetchone()
    return json.loads(row['widgets_json']) if row else ['accounts','cashflow','upcoming','budgets']


def save_widgets(widgets):
    allowed={'accounts','cashflow','upcoming','budgets'}
    if set(widgets)-allowed: raise ValueError('Choose known dashboard widgets.')
    db=get_db()
    db.execute('INSERT INTO app_preferences(id,widgets_json) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET widgets_json=excluded.widgets_json',(json.dumps(list(dict.fromkeys(widgets))),))
    db.commit()
