"""Account-backed reservations; only spending a completed pot changes the ledger."""
from datetime import date

from money_manager.db.atomic import atomic
from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances
from money_manager.utils.dates import add_frequency
from money_manager.utils.money import to_minor


def funding_accounts():
    db = get_db()
    reserved = {r['account_id']: r['total'] for r in db.execute("""
        SELECT s.account_id,SUM(s.reserved_minor) AS total FROM pot_sources s
        JOIN savings_pots p ON p.id=s.pot_id
        WHERE p.deleted_at IS NULL AND p.spent_at IS NULL GROUP BY s.account_id""")}
    return [dict(a, available=(to_minor(a['balance'])-reserved.get(a['id'], 0))/100)
            for a in account_balances() if a['is_active'] and a['type'] not in {'investment', 'credit_card'}]


def savings_summary():
    db = get_db()
    pots, spent, deleted = [], [], []
    available_accounts = funding_accounts()
    all_accounts = {a['id']:a for a in account_balances()}
    for pot in db.execute('SELECT * FROM savings_pots ORDER BY id DESC'):
        pot['sources'] = db.execute("""SELECT s.*,a.name AS account_name,a.is_active,
            s.reserved_minor/100.0 AS reserved FROM pot_sources s JOIN accounts a ON a.id=s.account_id
            WHERE pot_id=? AND reserved_minor>0 ORDER BY a.name""", (pot['id'],)).fetchall()
        pot['unattributed'] = (pot['reserved_minor']-sum(s['reserved_minor'] for s in pot['sources']))/100
        pot['movement_accounts'] = available_accounts + [dict(all_accounts[s['account_id']],available=0)
            for s in pot['sources'] if s['account_id'] not in {a['id'] for a in available_accounts}]
        pot['spending'] = db.execute("""SELECT s.*,a.name AS account_name,s.amount_minor/100.0 AS amount
            FROM pot_spending s JOIN accounts a ON a.id=s.account_id WHERE pot_id=? ORDER BY a.name""", (pot['id'],)).fetchall()
        movements = db.execute('SELECT * FROM pot_movements WHERE pot_id=? ORDER BY id DESC', (pot['id'],)).fetchall()
        for movement in movements[:8]:
            movement['sources'] = db.execute("""SELECT a.name,s.delta_minor/100.0 AS delta
                FROM pot_movement_sources s JOIN accounts a ON a.id=s.account_id WHERE movement_id=?""", (movement['id'],)).fetchall()
        pot['movements'] = movements[:8]
        monthly = {}
        for movement in movements:
            if movement['delta_minor'] > 0:
                key = movement['created_at'][:7]
                monthly[key] = monthly.get(key, 0)+movement['delta_minor']
        recent = list(monthly.values())[:3]
        remaining = max(0, pot['target_minor']-pot['reserved_minor'])
        pot['months_to_goal'] = int(remaining/(sum(recent)/len(recent))+0.999) if len(recent)>=2 and remaining else None
        pot['predicted_date'] = None
        if pot['months_to_goal'] and pot['months_to_goal'] <= 1200:
            predicted = date.today()
            for _ in range(pot['months_to_goal']):
                predicted = add_frequency(predicted, 'monthly')
            pot['predicted_date'] = predicted.isoformat()
        (deleted if pot['deleted_at'] else spent if pot['spent_at'] else pots).append(pot)
    reserved = sum(p['reserved_minor'] for p in pots)
    accounts = available_accounts
    balance = sum(to_minor(a['balance']) for a in accounts)
    return dict(pots=pots, spent=spent, deleted=deleted, accounts=accounts,
                reserved=reserved/100, balance=balance/100, unassigned=(balance-reserved)/100)


def _pot(pot_id):
    pot = get_db().execute('SELECT * FROM savings_pots WHERE id=?', (pot_id,)).fetchone()
    if not pot or pot['deleted_at'] or pot['spent_at']:
        raise ValueError('Choose an active savings pot.')
    return pot


def _sources(values):
    result = {}
    for account_id, amount in (values or {}).items():
        try:
            account_id = int(account_id)
        except (ValueError, TypeError):
            raise ValueError('Choose an existing source account.') from None
        minor = to_minor(amount or 0)
        if minor < 0:
            raise ValueError('Source amounts cannot be negative.')
        if minor:
            result[account_id] = result.get(account_id, 0)+minor
    return result


def _check_sources(sources, old=None, spending=False):
    old = old or {}
    accounts = {a['id']: a for a in funding_accounts()}
    for account_id, minor in sources.items():
        if not spending and minor <= old.get(account_id, 0):
            continue
        if account_id not in accounts:
            raise ValueError('Choose an active bank, cash, prepaid card, or wallet account.')
        if minor > max(0, to_minor(accounts[account_id]['available'])+old.get(account_id, 0)):
            raise ValueError(f"{accounts[account_id]['name']} doesn't have enough unreserved money. Choose another account or release a reservation.")


def _store_sources(pot_id, sources, movement_id=None):
    db = get_db()
    old = {r['account_id']: r['reserved_minor'] for r in db.execute('SELECT * FROM pot_sources WHERE pot_id=?', (pot_id,))}
    db.execute('DELETE FROM pot_sources WHERE pot_id=?', (pot_id,))
    for account_id, minor in sources.items():
        if minor:
            db.execute('INSERT INTO pot_sources VALUES (?,?,?)', (pot_id, account_id, minor))
    if movement_id:
        for account_id in old.keys() | sources.keys():
            delta = sources.get(account_id, 0)-old.get(account_id, 0)
            if delta:
                db.execute('INSERT INTO pot_movement_sources VALUES (?,?,?)', (movement_id, account_id, delta))


def save_pot(name, target, reserved, pot_id=None, note='', target_date='__keep__', sources=None):
    name = (name or '').strip()
    target, reserved = to_minor(target), to_minor(reserved)
    if not name or len(name)>100 or target<=0 or reserved<0:
        raise ValueError('Enter a name, a positive target, and a nonnegative reserved amount.')
    if len(note or '')>200:
        raise ValueError('Keep the movement note under 200 characters.')
    if target_date and target_date!='__keep__':
        try:
            date.fromisoformat(target_date)
        except ValueError:
            raise ValueError('Choose a valid goal date.') from None
    db = get_db()
    with atomic(db):
        old = _pot(pot_id) if pot_id else None
        old_reserved = old['reserved_minor'] if old else 0
        previous = {r['account_id']: r['reserved_minor'] for r in db.execute('SELECT * FROM pot_sources WHERE pot_id=?', (pot_id,))}
        supplied = sources is not None
        allocations = _sources(sources) if supplied else previous.copy()
        if supplied and sum(allocations.values()) != reserved:
            raise ValueError('The “Where from?” amounts must add up to the reserved amount.')
        if not supplied and previous and reserved != old_reserved:
            raise ValueError('Choose which accounts to add money from or release money to.')
        if supplied and allocations != previous:
            _check_sources(allocations, previous)
        summary = savings_summary()
        if reserved>old_reserved and to_minor(summary['reserved'])-old_reserved+reserved>max(0, to_minor(summary['balance'])):
            raise ValueError("There isn't enough unassigned money. Release another reservation first.")
        if target_date=='__keep__':
            target_date = old['target_date'] if old else None
        if old:
            db.execute('UPDATE savings_pots SET name=?,target_minor=?,reserved_minor=?,target_date=? WHERE id=?', (name,target,reserved,target_date or None,pot_id))
        else:
            pot_id = db.execute('INSERT INTO savings_pots (name,target_minor,reserved_minor,target_date) VALUES (?,?,?,?)', (name,target,reserved,target_date or None)).lastrowid
        movement = None
        if reserved != old_reserved:
            movement = db.execute('INSERT INTO pot_movements (pot_id,delta_minor,note) VALUES (?,?,?)', (pot_id,reserved-old_reserved,(note or '').strip())).lastrowid
        _store_sources(pot_id, allocations, movement)
    return pot_id


def move_pot(pot_id, amount, direction, note='', sources=None):
    db = get_db()
    with atomic(db):
        pot = _pot(pot_id)
        minor = to_minor(amount)
        if direction not in {'add','release'} or minor<=0:
            raise ValueError('Choose a movement and an amount greater than zero.')
        previous = {r['account_id']: r['reserved_minor'] for r in db.execute('SELECT * FROM pot_sources WHERE pot_id=?', (pot_id,))}
        if sources is None and not previous:
            return save_pot(pot['name'], pot['target'], (pot['reserved_minor']+(minor if direction=='add' else -minor))/100, pot_id, note)
        change = _sources(sources)
        if sum(change.values()) != minor:
            raise ValueError('The account amounts must add up to the movement amount.')
        updated = previous.copy()
        for account_id, value in change.items():
            updated[account_id] = updated.get(account_id, 0)+(value if direction=='add' else -value)
            if updated[account_id]<0:
                raise ValueError('You cannot release more than this account has reserved in the pot.')
        # Legacy reservations must be attributed before new account-backed movements.
        if sum(previous.values()) != pot['reserved_minor']:
            raise ValueError('Tell us where the existing money is first, then add or release money.')
        return save_pot(pot['name'], pot['target'], (pot['reserved_minor']+(minor if direction=='add' else -minor))/100,
                        pot_id, note, sources={k:v/100 for k,v in updated.items() if v})


def assign_sources(pot_id, sources):
    db = get_db()
    with atomic(db):
        pot = _pot(pot_id)
        return save_pot(pot['name'],pot['target'],pot['reserved'],pot_id,sources=sources)


def spend_pot(pot_id, confirmed=False):
    if not confirmed:
        raise ValueError('Tick the checkbox to record spending from your source accounts.')
    db = get_db()
    with atomic(db):
        pot = _pot(pot_id)
        if pot['reserved_minor'] < pot['target_minor']:
            raise ValueError('Reach the goal first. Your impulse purchases can wait.')
        sources = {r['account_id']: r['reserved_minor'] for r in db.execute('SELECT * FROM pot_sources WHERE pot_id=?', (pot_id,)) if r['reserved_minor']}
        if sum(sources.values()) != pot['reserved_minor']:
            raise ValueError('Choose where all the reserved money comes from before spending it.')
        _check_sources(sources, sources, spending=True)
        from money_manager.services.transactions import create_transaction
        for account_id, minor in sources.items():
            transaction = create_transaction(dict(date=date.today().isoformat(),type='expense',amount=minor/100,
                currency='EUR',account_id=account_id,description=f"Savings goal: {pot['name']}",status='posted'), commit=False)
            db.execute('INSERT INTO pot_spending VALUES (?,?,?,?)', (pot_id,account_id,transaction,minor))
        movement = db.execute('INSERT INTO pot_movements (pot_id,delta_minor,note) VALUES (?,?,?)',
                              (pot_id,-pot['reserved_minor'],'Goal spent. Finally.')).lastrowid
        _store_sources(pot_id, {}, movement)
        db.execute('UPDATE savings_pots SET reserved_minor=0,spent_at=CURRENT_TIMESTAMP WHERE id=?', (pot_id,))


def delete_pot(pot_id):
    db = get_db()
    with atomic(db):
        pot = db.execute('SELECT * FROM savings_pots WHERE id=?', (pot_id,)).fetchone()
        if not pot or pot['deleted_at']:
            raise ValueError('Savings pot not found.')
        db.execute('UPDATE savings_pots SET deleted_at=CURRENT_TIMESTAMP WHERE id=?', (pot_id,))


def restore_pot(pot_id):
    db = get_db()
    with atomic(db):
        pot = db.execute('SELECT * FROM savings_pots WHERE id=? AND deleted_at IS NOT NULL', (pot_id,)).fetchone()
        if not pot:
            raise ValueError('Choose a deleted pot to restore.')
        if not pot['spent_at']:
            sources = {r['account_id']:r['reserved_minor'] for r in db.execute('SELECT * FROM pot_sources WHERE pot_id=?', (pot_id,))}
            _check_sources(sources)
            summary = savings_summary()
            if pot['reserved_minor']>max(0,to_minor(summary['unassigned'])):
                raise ValueError('There is not enough unassigned money to restore this reservation.')
        db.execute('UPDATE savings_pots SET deleted_at=NULL WHERE id=?', (pot_id,))
