import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from money_manager.db.connection import get_db
from money_manager.db.atomic import atomic
from money_manager.utils.money import to_minor

RULES = {2024:(23,35,43),2025:(23,35,43),2026:(23,33,43)}
SOURCE = 'https://temi.camera.it/leg19/temi/19_tl18_irpef'


def tax_years():
    years = {date.today().year}
    years.update(r['tax_year'] for r in get_db().execute('SELECT tax_year FROM taxes UNION SELECT tax_year FROM tax_estimates'))
    return sorted(years,reverse=True)


def list_taxes(year):
    return get_db().execute('''SELECT t.*, amount_minor/100.0 AS amount,
        COALESCE((SELECT SUM(amount_minor) FROM tax_payments p WHERE p.tax_id=t.id),0)/100.0 AS paid,
        (amount_minor-COALESCE((SELECT SUM(amount_minor) FROM tax_payments p WHERE p.tax_id=t.id),0))/100.0 AS remaining
        FROM taxes t WHERE tax_year=? ORDER BY due_date,id''',(year,)).fetchall()


def get_tax(tax_id):
    return get_db().execute('''SELECT t.*, amount_minor/100.0 AS amount,
        COALESCE((SELECT SUM(amount_minor) FROM tax_payments p WHERE p.tax_id=t.id),0)/100.0 AS paid,
        (amount_minor-COALESCE((SELECT SUM(amount_minor) FROM tax_payments p WHERE p.tax_id=t.id),0))/100.0 AS remaining
        FROM taxes t WHERE id=?''',(tax_id,)).fetchone()


def save_tax(data, tax_id=None):
    name=(data.get('name') or '').strip()
    if not name or len(name)>100: raise ValueError('Give this tax a name of up to 100 characters.')
    amount=to_minor(data.get('amount') or 0)
    if amount<=0: raise ValueError('Amount must be greater than zero.')
    try:
        year=int(data.get('tax_year') or date.today().year)
        if not 1900<=year<=2200: raise ValueError()
        due=date.fromisoformat(data.get('due_date') or '')
    except (ValueError,TypeError): raise ValueError('Choose a valid tax year and due date.') from None
    authority=(data.get('authority') or '').strip(); notes=(data.get('notes') or '').strip()
    if len(authority)>100 or len(notes)>2000: raise ValueError('Use an authority up to 100 characters and notes up to 2,000 characters.')
    db=get_db()
    with atomic(db):
        values=(name,amount,due.isoformat(),year,authority,notes)
        if tax_id:
            old=get_tax(tax_id)
            if not old: raise ValueError('Tax not found.')
            if amount<to_minor(old['paid']): raise ValueError('Amount cannot be less than the payments already recorded.')
            db.execute('UPDATE taxes SET name=?,amount_minor=?,due_date=?,tax_year=?,authority=?,notes=? WHERE id=?',(*values,tax_id))
        else: tax_id=db.execute('INSERT INTO taxes(name,amount_minor,due_date,tax_year,authority,notes) VALUES(?,?,?,?,?,?)',values).lastrowid
    return tax_id


def record_payment(tax_id,data):
    db=get_db()
    with atomic(db):
        tax=get_tax(tax_id)
        if not tax: raise ValueError('Tax not found.')
        amount=to_minor(data.get('amount') or 0)
        if amount<=0 or amount>to_minor(tax['remaining']): raise ValueError('Payment must be positive and no more than the remaining tax.')
        try:
            paid_date=date.fromisoformat(data.get('date') or '')
            if paid_date>date.today(): raise ValueError()
        except (ValueError,TypeError): raise ValueError('Enter a valid payment date no later than today.') from None
        db.execute('INSERT INTO tax_payments(tax_id,date,amount_minor,notes) VALUES(?,?,?,?)',(tax_id,paid_date.isoformat(),amount,(data.get('notes') or '')[:2000]))


def calculate_irpef(data):
    try: year=int(data.get('tax_year') or date.today().year)
    except (ValueError,TypeError): raise ValueError('Choose a valid tax year.') from None
    if year not in RULES: raise ValueError('Calculator rates are verified for 2024–2026. Other years can still be tracked; their rates need an update before calculating.')
    values={key:to_minor(data.get(key) or 0) for key in ('income','deductions','credits','local_tax','withheld')}
    if any(v<0 for v in values.values()): raise ValueError('Amounts cannot be negative.')
    if values['deductions']>values['income']: raise ValueError('Deductions cannot exceed income.')
    taxable=values['income']-values['deductions']; lower=0; exact=Decimal(0); breakdown=[]
    for upper,rate in zip((2800000,5000000,max(taxable,5000000)),RULES[year]):
        portion=max(0,min(taxable,upper)-lower)
        tax=Decimal(portion)*Decimal(rate)/100
        exact+=tax
        breakdown.append(dict(lower=lower/100,upper=None if lower==5000000 else upper/100,rate=rate,portion=portion/100,tax=float(tax/100)))
        lower=upper
    gross=int(exact.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    net=max(0,gross-values['credits'])
    total=net+values['local_tax']; balance=total-values['withheld']
    result=dict(tax_year=year,taxable=taxable/100,gross=gross/100,net=net/100,total=total/100,balance=balance/100,breakdown=breakdown,source=SOURCE,
                rules_version=f'IT-IRPEF-{year}-verified-2026-10-03',effective_rate=round(gross/taxable*100,2) if taxable else 0)
    return dict(tax_year=year,**{k:v/100 for k,v in values.items()}),result


def save_estimate(data):
    inputs,result=calculate_irpef(data)
    with atomic(get_db()):
        return get_db().execute('INSERT INTO tax_estimates(tax_year,inputs_json,result_json,rules_version) VALUES(?,?,?,?)',
                                (result['tax_year'],json.dumps(inputs),json.dumps(result),result['rules_version'])).lastrowid


def list_estimates(year):
    return [dict(row,result=json.loads(row['result_json'])) for row in get_db().execute('SELECT * FROM tax_estimates WHERE tax_year=? ORDER BY id DESC',(year,))]
