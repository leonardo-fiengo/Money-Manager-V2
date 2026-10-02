from money_manager.utils.money import money_value, to_minor
from uuid import uuid4
from datetime import date

from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances


def balance_at(account_id, through_date):
    db=get_db()
    account=db.execute('SELECT opening_balance_minor FROM accounts WHERE id=?',(account_id,)).fetchone()
    if not account: raise ValueError('Account not found.')
    total=account['opening_balance_minor']
    for tx in db.execute("SELECT t.* FROM transactions t WHERE status='posted' AND date<=? AND (account_id=? OR destination_account_id=?)",(through_date,account_id,account_id)):
        if tx['type']=='transfer':
            if tx['destination_account_id']==int(account_id):
                paired=db.execute("SELECT 1 FROM transaction_relationships WHERE kind='transfer_pair' AND source_transaction_id=?",(tx['id'],)).fetchone()
                if not paired: total+=tx['amount_eur_minor']
            else: total-=tx['amount_eur_minor']
        elif tx['account_id']==int(account_id): total+=tx['amount_eur_minor']*(1 if tx['type']=='income' else -1)
    total+=db.execute("SELECT COALESCE(SUM(b.adjustment_minor),0) AS total FROM balance_checks b LEFT JOIN reconciliation_sessions s ON s.id=b.session_id WHERE b.account_id=? AND COALESCE(s.through_date,substr(b.created_at,1,10))<=?",(account_id,through_date)).fetchone()['total']
    return total/100


def preview_balances(values, through_date=None):
    through_date=through_date or date.today().isoformat()
    try:
        if date.fromisoformat(through_date)>date.today(): raise ValueError()
    except ValueError: raise ValueError('Choose a balance date no later than today.') from None
    rows = []
    db = get_db()
    for account in account_balances():
        value = values.get(str(account["id"]), "")
        if not str(value).strip():
            continue
        account['balance']=balance_at(account['id'],through_date)
        account['through_date']=through_date
        actual = money_value(value)
        delta = round(actual - account["balance"], 2)
        hints = []
        pending = db.execute(
            "SELECT COUNT(*) AS count FROM ledger_transactions WHERE status = 'pending' AND (account_id = ? OR destination_account_id = ?)",
            (account["id"], account["id"]),
        ).fetchone()["count"]
        if pending:
            hints.append(f"{pending} pending payment(s) are excluded from the app balance. Compare with your bank's booked balance, before pending holds.")
        duplicates = db.execute(
            "SELECT COUNT(*) AS count FROM (SELECT date, amount_eur, type, merchant_id, description FROM ledger_transactions "
            "WHERE account_id = ? AND status = 'posted' GROUP BY date, amount_eur, type, merchant_id, description HAVING COUNT(*) > 1)",
            (account["id"],),
        ).fetchone()["count"]
        if delta and duplicates:
            hints.append(f"{duplicates} group(s) of similar entries could be duplicates. Review them before adjusting.")
        if delta:
            hints.append("A missing expense or an overstated income could explain this." if delta < 0 else "A missing income or an extra expense could explain this.")
        candidates=[]
        if delta:
            candidates=db.execute("""SELECT t.id,t.date,t.description,t.amount_eur,t.type,
                EXISTS(SELECT 1 FROM ledger_transactions other WHERE other.id!=t.id AND other.date=t.date AND other.account_id=t.account_id AND other.amount_eur_minor=t.amount_eur_minor AND other.type=t.type AND COALESCE(other.description,'')=COALESCE(t.description,'')) AS possible_duplicate
                FROM ledger_transactions t WHERE t.status='posted' AND t.date<=? AND t.account_id=? AND t.reconciled_session_id IS NULL
                AND t.amount_eur_minor=? AND ((?>0 AND t.type IN('expense','investment')) OR (?<0 AND t.type='income'))
                ORDER BY possible_duplicate DESC,t.date DESC LIMIT 10""",(through_date,account['id'],abs(to_minor(delta)),delta,delta)).fetchall()
        rows.append(dict(account, actual=actual, difference=delta, hints=hints, candidates=candidates))
    if not rows:
        raise ValueError("Enter an actual balance for at least one account.")
    for row in rows:
        matches = [other["name"] for other in rows if other["id"] != row["id"] and row["difference"] and abs(other["difference"] + row["difference"]) < 0.005]
        if matches:
            row["hints"].insert(0, f"An opposite difference in {', '.join(matches)} could mean a payment used the wrong account or a transfer is missing.")
    return rows


def check_payload(rows):
    return {"batch_id": str(uuid4()), "rows": [
        {"id": r["id"], "expected": r["balance"], "actual": r["actual"], "through_date":r.get("through_date",date.today().isoformat())} for r in rows
    ]}


def record_checks(payload, adjust_ids, note):
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM balance_checks WHERE batch_id = ?", (payload["batch_id"],)).fetchone():
            raise ValueError("This balance check has already been saved.")
        balances = {a["id"]: a for a in account_balances()}
        allowed = {str(r["id"]) for r in payload["rows"]}
        if not set(adjust_ids).issubset(allowed):
            raise ValueError("Invalid adjustment selection. Check balances again.")
        for row in payload["rows"]:
            account = balances.get(row["id"])
            through=row.get('through_date',date.today().isoformat())
            if not account or abs(balance_at(row['id'],through) - row["expected"]) > 0.005:
                raise ValueError("An account balance changed since this preview. Check balances again before saving.")
            delta = round(row["actual"] - row["expected"], 2) if str(row["id"]) in adjust_ids else 0
            status='closed' if to_minor(row['actual'])==to_minor(row['expected'])+to_minor(delta) else 'open'
            session_id=db.execute("INSERT INTO reconciliation_sessions(account_id,through_date,expected_minor,actual_minor,adjustment_minor,note,status) VALUES(?,?,?,?,?,?,?)",(row['id'],through,to_minor(row['expected']),to_minor(row['actual']),to_minor(delta),note.strip()[:500],status)).lastrowid
            if status=='closed':
                db.execute("INSERT INTO reconciliation_transactions(session_id,transaction_id) SELECT ?,id FROM transactions WHERE status='posted' AND date<=? AND (account_id=? OR destination_account_id=?)",(session_id,through,row['id'],row['id']))
                db.execute("UPDATE transactions SET reconciled_session_id=? WHERE status='posted' AND date<=? AND (account_id=? OR destination_account_id=?)",(session_id,through,row['id'],row['id']))
            db.execute(
                "INSERT INTO balance_checks (account_id, expected_minor, actual_minor, adjustment_minor, note, batch_id) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], to_minor(row["expected"]), to_minor(row["actual"]), to_minor(delta), note.strip()[:500], payload["batch_id"]),
            )
            db.execute('UPDATE balance_checks SET session_id=? WHERE batch_id=? AND account_id=?',(session_id,payload['batch_id'],row['id']))
        db.commit()
    except Exception:
        db.rollback()
        raise


def check_history():
    return get_db().execute(
        "SELECT b.*, a.name AS account_name FROM balance_checks b JOIN accounts a ON a.id = b.account_id ORDER BY b.id DESC LIMIT 50"
    ).fetchall()


def reconciliation_history():
    return get_db().execute('SELECT s.*,a.name AS account_name,(SELECT COUNT(*) FROM reconciliation_transactions t WHERE t.session_id=s.id) AS transaction_count FROM reconciliation_sessions s JOIN accounts a ON a.id=s.account_id ORDER BY s.id DESC LIMIT 100').fetchall()


def reopen_session(session_id):
    db=get_db()
    with db:
        if not db.execute('SELECT 1 FROM reconciliation_sessions WHERE id=?',(session_id,)).fetchone(): raise ValueError('Session not found.')
        db.execute("UPDATE reconciliation_sessions SET status='open' WHERE id=?",(session_id,))
        db.execute("UPDATE transactions SET reconciled_session_id=(SELECT MAX(rt.session_id) FROM reconciliation_transactions rt JOIN reconciliation_sessions s ON s.id=rt.session_id WHERE rt.transaction_id=transactions.id AND s.status='closed') WHERE reconciled_session_id=?",(session_id,))
