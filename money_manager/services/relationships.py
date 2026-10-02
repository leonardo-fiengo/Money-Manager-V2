import json

from money_manager.db.atomic import atomic
from money_manager.db.connection import get_db
from money_manager.services.accounts import account_balances


def transfer_candidates():
    return get_db().execute("""SELECT e.id AS outgoing_id,i.id AS incoming_id,e.date,e.amount_eur,
        e.description AS outgoing_description,i.description AS incoming_description,
        a.name AS from_account,b.name AS to_account
        FROM ledger_transactions e JOIN ledger_transactions i ON i.type='income'
        AND i.account_id!=e.account_id AND i.amount_eur_minor=e.amount_eur_minor
        AND abs(julianday(i.date)-julianday(e.date))<=3
        JOIN accounts a ON a.id=e.account_id JOIN accounts b ON b.id=i.account_id
        WHERE e.type='expense' AND e.status='posted' AND i.status='posted'
        AND e.is_credit_card_settlement=0 AND e.recurring_rule_id IS NULL AND i.recurring_rule_id IS NULL
        AND NOT EXISTS(SELECT 1 FROM transaction_relationships r WHERE r.kind='transfer_pair' AND
        (r.source_transaction_id IN(e.id,i.id) OR r.related_transaction_id IN(e.id,i.id)))
        ORDER BY e.date DESC,e.id DESC LIMIT 100""").fetchall()


def match_transfer(outgoing_id,incoming_id):
    db=get_db()
    with atomic(db):
        outgoing=db.execute('SELECT * FROM transactions WHERE id=?',(outgoing_id,)).fetchone()
        incoming=db.execute('SELECT * FROM transactions WHERE id=?',(incoming_id,)).fetchone()
        if not outgoing or not incoming or outgoing['type']!='expense' or incoming['type']!='income' or outgoing['account_id']==incoming['account_id'] or outgoing['amount_eur_minor']!=incoming['amount_eur_minor'] or outgoing['status']!='posted' or incoming['status']!='posted' or outgoing['is_transfer_mirror'] or incoming['is_transfer_mirror']:
            raise ValueError('Choose a posted expense and matching income in different accounts with equal EUR amounts.')
        for tx in (outgoing,incoming):
            if tx['reconciled_session_id'] or tx['is_credit_card_settlement'] or db.execute('SELECT 1 FROM transactions WHERE settlement_for_transaction_id=?',(tx['id'],)).fetchone() or db.execute('SELECT 1 FROM transaction_splits WHERE transaction_id=?',(tx['id'],)).fetchone() or db.execute('SELECT 1 FROM transaction_links WHERE source_transaction_id=? OR related_transaction_id=?',(tx['id'],tx['id'])).fetchone() or db.execute("SELECT 1 FROM transaction_relationships WHERE kind='transfer_pair' AND (source_transaction_id=? OR related_transaction_id=?)",(tx['id'],tx['id'])).fetchone():
                raise ValueError('Unlink or reopen this payment before matching a transfer. Split and settled payments cannot be merged.')
        before={a['id']:a['balance'] for a in account_balances()}
        cursor=db.execute("INSERT INTO transaction_relationships(source_transaction_id,related_transaction_id,kind,originals_json) VALUES(?,?,'transfer_pair',?)",(outgoing_id,incoming_id,json.dumps([outgoing,incoming])))
        db.execute("UPDATE transactions SET type='transfer',destination_account_id=?,category=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(incoming['account_id'],outgoing_id))
        db.execute('UPDATE transactions SET is_transfer_mirror=1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(incoming_id,))
        if before!={a['id']:a['balance'] for a in account_balances()}:
            raise ValueError('The match would change account balances. Nothing was saved.')
    return cursor.lastrowid


def unmatch_transfer(relationship_id):
    db=get_db()
    with atomic(db):
        row=db.execute("SELECT * FROM transaction_relationships WHERE id=? AND kind='transfer_pair'",(relationship_id,)).fetchone()
        if not row or not row['originals_json']:
            raise ValueError('This transfer match no longer exists.')
        for original in json.loads(row['originals_json']):
            current=db.execute('SELECT * FROM transactions WHERE id=?',(original['id'],)).fetchone()
            if not current or current['reconciled_session_id']:
                raise ValueError('Reopen the reconciliation session before unmatching this transfer.')
            db.execute('UPDATE transactions SET type=?,destination_account_id=?,category=?,is_transfer_mirror=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(original['type'],original['destination_account_id'],original['category'],original['is_transfer_mirror'],original['id']))
        db.execute('DELETE FROM transaction_relationships WHERE id=?',(relationship_id,))


def relationships_for(transaction_id):
    return get_db().execute("SELECT * FROM transaction_relationships WHERE source_transaction_id=? OR related_transaction_id=?",(transaction_id,transaction_id)).fetchall()
