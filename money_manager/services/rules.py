import json
import re

import regex

from money_manager.db.connection import get_db
from money_manager.utils.money import to_minor


def normalized(value):
    return re.sub(r'\s+', ' ', (value or '').casefold()).strip()


def merchant_match(description):
    text = normalized(description)
    db = get_db()
    alias = db.execute('SELECT m.* FROM merchant_aliases a JOIN merchants m ON m.id=a.merchant_id WHERE a.normalized=?', (text,)).fetchone()
    if alias:
        return alias
    candidates = [(r['normalized'], r['merchant_id']) for r in db.execute('SELECT * FROM merchant_aliases')]
    candidates += [(normalized(r['name']), r['id']) for r in db.execute('SELECT id,name FROM merchants')]
    for needle, merchant_id in sorted(candidates, key=lambda r: len(r[0]), reverse=True):
        if needle and needle in text:
            return db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone()
    return None


def save_alias(merchant_id, alias, commit=True):
    alias = (alias or '').strip()
    db = get_db()
    if not alias or len(alias) > 500 or not db.execute('SELECT 1 FROM merchants WHERE id=?', (merchant_id,)).fetchone():
        raise ValueError('Choose a merchant and an alias under 500 characters.')
    db.execute('INSERT INTO merchant_aliases(merchant_id,alias,normalized) VALUES(?,?,?) ON CONFLICT(normalized) DO UPDATE SET merchant_id=excluded.merchant_id,alias=excluded.alias', (merchant_id, alias, normalized(alias)))
    if commit:
        db.commit()


def list_finance_rules():
    return [dict(row, conditions=json.loads(row['conditions_json']), actions=json.loads(row['actions_json'])) for row in get_db().execute('SELECT * FROM finance_rules ORDER BY priority DESC,id DESC')]


def parse_rule(form):
    conditions = {k: (form.get(k) or '').strip() for k in ('contains', 'merchant_contains', 'pattern', 'account_id', 'direction', 'currency', 'day', 'month', 'min_amount', 'max_amount')}
    conditions = {k: v for k, v in conditions.items() if v}
    actions = {k: (form.get(k) or '').strip() for k in ('merchant_id', 'category', 'tags', 'rename')}
    actions.update(ignore=bool(form.get('ignore')), subscription=bool(form.get('subscription')))
    name = (form.get('name') or '').strip()
    try:
        priority = int(form.get('priority') or 0)
    except ValueError:
        raise ValueError('Priority must be a whole number.') from None
    validate_rule(name, priority, conditions, actions)
    return name, priority, conditions, actions


def validate_rule(name, priority, conditions, actions):
    if not name or len(name)>100 or not -10000<=priority<=10000 or not conditions:
        raise ValueError('Enter a name, a priority between -10000 and 10000, and at least one condition.')
    db=get_db()
    if len(conditions.get('contains',''))>200 or len(conditions.get('pattern',''))>200:
        raise ValueError('Match text and patterns must be under 200 characters.')
    if conditions.get('pattern'):
        try:
            regex.compile(conditions['pattern'])
        except regex.error:
            raise ValueError('The regular expression is invalid.') from None
    for key, table, value in [('account_id','accounts',conditions.get('account_id')),('merchant_id','merchants',actions.get('merchant_id'))]:
        if value and not db.execute(f'SELECT 1 FROM {table} WHERE id=?',(value,)).fetchone():
            raise ValueError(f'Choose an existing {table[:-1]}.')
    for key, maximum in [('day',31),('month',12)]:
        if conditions.get(key) and (not str(conditions[key]).isdigit() or not 1<=int(conditions[key])<=maximum):
            raise ValueError(f'Choose a {key} from 1 to {maximum}.')
    if conditions.get('direction') not in {None,'expense','income','investment','transfer'} or conditions.get('currency') not in {None,'EUR','USD','GBP','CHF'}:
        raise ValueError('Choose a transaction direction and supported currency.')
    for key in ('min_amount','max_amount'):
        if conditions.get(key) is not None and to_minor(conditions[key])<0:
            raise ValueError('Amount limits cannot be negative.')
    if 'min_amount' in conditions and 'max_amount' in conditions and to_minor(conditions['min_amount'])>to_minor(conditions['max_amount']):
        raise ValueError('Minimum amount must not exceed the maximum.')
    if actions.get('category') and not db.execute('SELECT 1 FROM categories WHERE name=?',(actions['category'],)).fetchone():
        raise ValueError('Choose an existing category.')
    tags=[t.strip() for t in actions.get('tags','').split(',') if t.strip()]
    if len(tags)>8 or any(len(t)>40 for t in tags) or len(actions.get('rename',''))>500:
        raise ValueError('Use at most 8 tags under 40 characters and a description under 500 characters.')
    if not any(actions.values()):
        raise ValueError('Choose at least one action.')


def matches(item, conditions):
    description=item.get('description') or ''
    if conditions.get('contains') and normalized(conditions['contains']) not in normalized(description): return False
    if conditions.get('merchant_contains'):
        merchant=item.get('merchant_name')
        if not merchant and item.get('merchant_id'):
            row=get_db().execute('SELECT name FROM merchants WHERE id=?',(item['merchant_id'],)).fetchone()
            merchant=row['name'] if row else ''
        if normalized(conditions['merchant_contains']) not in normalized(merchant): return False
    if conditions.get('pattern'):
        try:
            if not regex.search(conditions['pattern'], description[:2000], regex.IGNORECASE, timeout=.02): return False
        except TimeoutError:
            raise ValueError('This regular expression takes too long. Simplify the pattern.') from None
    for key, field in [('account_id','account_id'),('direction','type'),('currency','currency')]:
        if conditions.get(key) and str(conditions[key])!=str(item.get(field)): return False
    for key, section in [('day',slice(8,10)),('month',slice(5,7))]:
        if conditions.get(key) and int(conditions[key])!=int(item['date'][section]): return False
    amount=to_minor(item.get('amount',0))
    if 'min_amount' in conditions and amount<to_minor(conditions['min_amount']): return False
    if 'max_amount' in conditions and amount>to_minor(conditions['max_amount']): return False
    return True


def apply_rules(item):
    item=dict(item)
    for rule in list_finance_rules():
        if rule['is_active'] and matches(item,rule['conditions']):
            action=rule['actions']
            for key in ('merchant_id','category'):
                if action.get(key): item[key]=action[key]
            if action.get('rename'): item['description']=action['rename']
            item.update(tags=action.get('tags',''),is_subscription=bool(action.get('subscription')),ignored=bool(action.get('ignore')),matched_rule=rule['name'])
            break
    return item


def save_finance_rule(form):
    name,priority,conditions,actions=parse_rule(form)
    db=get_db()
    cursor=db.execute('INSERT INTO finance_rules(name,priority,conditions_json,actions_json) VALUES(?,?,?,?)',(name,priority,json.dumps(conditions),json.dumps(actions)))
    db.commit()
    return cursor.lastrowid


def preview_rule(form):
    _,_,conditions,actions=parse_rule(form)
    rows=get_db().execute('SELECT t.*,m.name AS merchant_name FROM transactions t LEFT JOIN merchants m ON m.id=t.merchant_id ORDER BY t.date DESC,t.id DESC LIMIT 5000').fetchall()
    return [dict(row, proposed=actions) for row in rows if matches(row,conditions)]
