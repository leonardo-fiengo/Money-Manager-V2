from money_manager.db.connection import get_db
from money_manager.db.atomic import atomic
from money_manager.services.rules import apply_rules, merchant_match, save_alias


def review_suggestions(rows):
    results = []
    for row in rows:
        item = dict(row)
        try:
            proposed = apply_rules(item)
        except ValueError:
            proposed = item
        merchant = merchant_match(item.get('description'))
        item['suggested_category'] = proposed.get('category') or (merchant['default_category'] if merchant else None)
        item['suggested_merchant'] = proposed.get('merchant_id') or (merchant['id'] if merchant else None)
        item['matched_rule'] = proposed.get('matched_rule')
        item['can_categorize'] = not item['category'] and item['type'] == 'expense' and bool(get_db().execute('SELECT 1 FROM transaction_import_hashes WHERE transaction_id=?', (item['id'],)).fetchone())
        results.append(item)
    return results


def categorize_review(transaction_ids, category, merchant_id=None, remember=False):
    try:
        ids = list(dict.fromkeys(int(value) for value in transaction_ids))
        merchant_id = int(merchant_id) if merchant_id else None
    except (ValueError, TypeError):
        raise ValueError('Choose valid transactions and a merchant.') from None
    if not 1 <= len(ids) <= 50:
        raise ValueError('Select between 1 and 50 uncategorized imports.')
    db = get_db()
    with atomic(db):
        if not db.execute('SELECT 1 FROM categories WHERE name=?', (category,)).fetchone():
            raise ValueError('Choose an existing category.')
        if merchant_id and not db.execute('SELECT 1 FROM merchants WHERE id=?', (merchant_id,)).fetchone():
            raise ValueError('Choose an existing merchant.')
        for transaction_id in ids:
            row = db.execute("SELECT t.* FROM ledger_transactions t WHERE t.id=? AND t.type='expense' AND t.category IS NULL AND EXISTS (SELECT 1 FROM transaction_import_hashes h WHERE h.transaction_id=t.id)", (transaction_id,)).fetchone()
            if not row or db.execute('SELECT 1 FROM transaction_splits WHERE transaction_id=?', (transaction_id,)).fetchone():
                raise ValueError('This selection changed or includes a split expense. Refresh and review it individually.')
            db.execute('UPDATE transactions SET category=?,merchant_id=COALESCE(?,merchant_id),contact_id=CASE WHEN ? IS NOT NULL THEN NULL ELSE contact_id END,updated_at=CURRENT_TIMESTAMP WHERE id=?', (category, merchant_id, merchant_id, transaction_id))
            if remember and merchant_id and row['description']:
                save_alias(merchant_id, row['description'], commit=False)
    return len(ids)
